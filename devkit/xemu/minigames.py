"""Dev-only solvers for Azurik's progression minigames on the xemu oracle
(Step R1.8f): each plays one minigame with real pad input in closed loop,
reading the minigame's state from guest RAM.

A sitting script (``uv run --locked python`` from the checkout's root)
puts the player at a minigame (walked there with ``devkit.xemu.route`` or
placed), then::

    from devkit.xemu import oracle as xo, minigames as mg
    m = mg.Minigames(sb, iso, "w2")                # the level's graph and collision, its live nodes
    m.hose()                                       # -> {"solved": True, ...}

The minigames (``docs/RANDOMIZER.md`` "Minigames"; each one's wiring is in
its realm's ``devkit/rando/draft/authoring/<level>.toml``):

* :meth:`Minigames.hose` (w2): X at the console turns the water on; at
  the joystick the stick's deflection is the nozzle's angle and range;
  water in a fire's sink puts it out for about 8 s and all six out at once
  latch ``HoseStuff:hosetoggle``.  :data:`Minigames.HOSE_PLAN`'s holds
  and sweeps (found by cooled sweeps in sitting r18f) put them out in one
  round; the water lands 3-5 s after the aim.
* :meth:`Minigames.aim_light` (e6 spotlights) and :meth:`Minigames.laser`
  (a6): the stick sets the rates of a light's two aims; a target is lit
  while both sit in their windows, read from the link curves of the AND
  combiner that checks them (:meth:`window`).  A controller drives each
  into the middle half of its window (:meth:`drive`, with a brake for a
  damped aim; :meth:`drive_rate`, proportional for a direct one).
* :meth:`Minigames.song` (e6): seven staff hits on the giant crystal in
  the order the data's ``Tone01..07_solution_toggle`` windows give
  (:meth:`song_order`); each staff is an LT combo (:meth:`select`: the
  combo is exactly the buttons pressed while LT is held), A attacks, and
  the tone each hit latched is read back.
* :meth:`Minigames.cannon` (a5): aims the barrel at each smokestack's ice
  sink, led for its sub-main's turn, while the cannon fires itself;
  a stack the aim holds for three shots without a hit gets a pitch step.
* :meth:`Minigames.cores` (life): steers the pilot ball's latitude onto
  the next filament core ahead (unfinished: sitting r18f lit 3 of 20).
* :meth:`Minigames.spotlights` (e6, Step R1.8i): both machines in the
  owner's order (:data:`Minigames.SPOTLIGHT_ORDER`: red from the lower
  ring, the red lift up, upper-ring lights onto red and blue orbs, back
  down, the last two onto blue), each light engaged where its joystick
  stands now (it rises 1.5 m once its pad's mirror toggle runs);
  :meth:`Minigames.lift` rides the red lift and :meth:`Minigames.vent_beam`
  launches from the upper ring's steam vent into the blue beam, which
  carries the player to frag_earth_3.
* :meth:`Minigames.torpedo` (w1, Step R1.8h): at the periscope, turns it
  onto the tower (:meth:`torpedo_window`: the PeriscopeTimer interval
  StatueRotToggle accepts, read from the link curves), lets go of the
  joystick, which launches the torpedo, and watches the tower fall and the
  wall in front of the dark cave go.

What sitting r18f measured, which the solvers rest on: a platform's
joystick reads the left stick in a different part of the frame from the
player's input build, so the stick is written right after the main loop's
pad poll returns (:data:`POLL_RET`); X reaches the object the game's
interaction test picks (0x4E870: the body centre within 1.5 m of the
object's bounding sphere, faced within 30 degrees), and from some sides
another object wins, so a sitting may need a second approach; and a
transform's node keeps no attribute block where other nodes keep theirs,
so a moving transform is computed from the links that drive it
(:meth:`xform_live`).

Inputs: the left stick through ``Sandbox.write_pad`` (the one RAM pad
writer), buttons through the input FIFO.  The solvers read RAM and never
write it.  Dev only (devkit, Step 4.13d2), a library, never in pytest (D11); the sandbox rules are
the ``azurik-xemu-oracle`` skill's.  Nothing they return or print holds a
coordinate: names, counts, distances, timer and stick values only.  USA
VAs (the sandbox's disc).
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

from azurkit.tools.randomizer.art import collision
from azurkit.tools.randomizer.art import nodes as N
from azurkit.tools.randomizer.levels import link_curve, link_value
from azurkit.tools.randomizer.live import recipes
from devkit.sim import l3
from devkit.sim.ports import XisoReader
from devkit.xemu import oracle as xo
from devkit.xemu import route as xr

POLL_RET = 0xA2EB6          # the instruction after the main loop's CALL to the pad poll 0xA2880 (its only caller)
SCENE, PD, GRAPH, VEC, ATTRS = 0x1BF63C, 0x2C, 0xDC, 0x24, 0x08
ARMOR_MGR, STAFF_MASK, CRITTER, BODY, YAW = 0xCC, 0x1C, 0xC0, 0x15C, 0x90
ELEM = {"earth": 1, "air": 2, "fire": 4, "water": 8}
PICK = {"earth": "a", "air": "y", "fire": "b", "water": "x"}   # LT + this adds the element [verified xemu rz-b1, r18f]
STAFF = {"fire": ("earth", "fire"), "smash": ("earth", "air", "fire"),
         "lightning": ("air", "fire", "water"), "whirlwind": ("earth", "air"),
         "elem": ("earth", "air", "fire", "water")}   # config.xbr magic (elem: EAFW, never blocked by an armor AI)
TONE = {"fire": 1, "smash": 2, "lightning": 3, "whirlwind": 4}   # WhichWackType_max's inputs
REACH_M = 1.5               # 0x4E870's range past the object's bounding sphere ([0x1A26C4])
DIALOG = ("no player tick", "no stop within")


class Minigames:
    """One level's minigames on a sandbox: its graph (names, attributes,
    links) and collision read from the vanilla ISO, its nodes read live."""

    def __init__(self, sb, iso, level: str):
        from azurkit.tools.randomizer.draft.geometry import Level as GLevel
        self.sb, self.level = sb, level
        with XisoReader(Path(iso)) as rd:
            xbe = bytes(rd.read_file("default.xbe"))
            data = bytes(rd.read_file(f"gamedata/{level}.xbr"))
        self.schema = N.Schema(xbe)
        self.graphs = N.graphs(data, self.schema)
        self.geo = GLevel(level, collision.owners(data, self.schema, self.graphs), self.graphs)
        self.stick = (0.0, 0.0)
        self.relink()

    # ---- the graph and its live nodes
    def relink(self) -> None:
        """Bind to the loaded level's main graph ([pd+0xDC]); call after a level load."""
        sb = self.sb
        self.pd = sb.read_u32(sb.read_u32(SCENE) + PD)
        graph = sb.read_u32(self.pd + GRAPH)
        b, e = struct.unpack("<II", sb.read(graph + VEC, 8))
        match = [gi for gi, g in enumerate(self.graphs) if len(g.recs) == (e - b) // 4]
        if not match:
            raise SystemExit(f"{self.level}: no graph of the level has the live graph's {(e - b) // 4} nodes")
        self.gi, self.g, self.vec = match[0], self.graphs[match[0]], b
        self.by: dict[str, list[int]] = {}
        for i, nm in enumerate(self.g.names):
            self.by.setdefault(nm, []).append(i)
        self._ap: dict[int, int] = {}       # record -> its attribute block (fixed while the level is loaded)
        self.inc: dict[int, list] = {}
        for i in range(len(self.g.recs)):
            if self.g.recs[i] is not None:
                for k, lk in enumerate(self.g.links(i)):
                    self.inc.setdefault(lk.dst, []).append((i, lk, k))

    def find(self, name: str | int) -> int:
        if isinstance(name, int):
            return name
        hits = self.by.get(name, [])
        if len(hits) != 1:
            raise KeyError(f"{self.level}: {len(hits)} records named {name!r}")
        return hits[0]

    def _block(self, i: int) -> int:
        if i not in self._ap:
            self._ap[i] = self.sb.read_u32(self.sb.read_u32(self.vec + 4 * i) + ATTRS)
        return self._ap[i]

    def attrs(self, name) -> dict[str, float]:
        i = self.find(name)
        names = self.schema.types[self.g.types[i]].attrs
        n = len(self.g.attrs(i))
        return dict(zip(names, struct.unpack(f"<{n}f", self.sb.read(self._block(i), 4 * n)))) if n else {}

    def get(self, name, attr: str) -> float:
        i = self.find(name)
        k = self.schema.types[self.g.types[i]].attrs.index(attr)
        if 1 <= k <= 9 and self.schema.is_a(self.g.types[i], "transform"):
            return self.xform_live(i)[k]          # a transform's node keeps no attribute block (xform_live)
        return struct.unpack("<f", self.sb.read(self._block(i) + 4 * k, 4))[0]

    def ins(self, name):
        """(source record, link, k, source plug, target plug) of each link into ``name``."""
        j = self.find(name)
        return [(i, lk, k, self.g.plug_name(i, lk.src_plug), self.g.plug_name(j, lk.dst_plug))
                for i, lk, k in self.inc.get(j, [])]

    def mesh(self, name):
        """The collision mesh's vertices of a platform record (in memory)."""
        import numpy as np
        oi = self.geo.by_rec[(self.gi, self.find(name))]
        return np.asarray(self.geo.P[self.geo.tris_of(oi)]).reshape(-1, 3)

    def mesh_live(self, name):
        """The mesh where its transforms stand now (a pad a timer lowered,
        say): the level's mesh moved by the live parent matrix against the
        level's own (in memory)."""
        import numpy as np
        i = self.find(name)
        q = self.mesh(i)
        par = self.g.parent(i)
        if par is None:
            return q
        m = np.array(self.live_world(par)) @ np.linalg.inv(np.array(self.g.world(par)[0]))
        return (np.c_[q, np.ones(len(q))] @ m.T)[:, :3]

    def body(self) -> tuple:
        c = self.sb.read_u32(self.pd + CRITTER)
        return struct.unpack("<3f", self.sb.read(c + BODY, 12))

    def loaded(self) -> str:
        """The level the game has loaded (pd's path): not this one's after a death reloaded the save."""
        return self.sb.read(self.pd, 0x50).split(b"\0")[0].decode("latin-1")

    def hp(self) -> int:
        """The player's HP (the critter's)."""
        return struct.unpack("<i", self.sb.read(self.sb.read_u32(self.pd + CRITTER) + recipes.CR_HP, 4))[0]

    def staff_mask(self) -> int:
        return struct.unpack("<i", self.sb.read(self.sb.read_u32(self.pd + ARMOR_MGR) + STAFF_MASK, 4))[0]

    # ---- input
    def _hook(self, sb, regs) -> None:
        sb.write_pad(l3.Pad(stick=self.stick), stick_only=True)

    def run(self, n: int, *, stick=None, schedule=None, on_tick=None, hook_at: int = POLL_RET) -> dict:
        """``n`` player ticks with the left stick held at ``stick`` (or as
        ``on_tick`` sets ``self.stick``), the stick written at ``hook_at``;
        a dialog that stops the player tick is cleared (A) and the run goes
        on. Returns the last capture's meta."""
        if stick is not None:
            self.stick = tuple(stick)
        meta = {}
        for _ in range(4):
            cap = self.sb.capture(n, schedule, on_tick=on_tick, chain=False, hooks={hook_at: self._hook})
            meta = cap["meta"]
            if meta["stop"] and any(d in meta["stop"] for d in DIALOG):
                xr.clear_dialog(self.sb)
                continue
            break
        return meta

    def cam_yaw(self) -> float:
        g = self.sb.g
        return math.degrees(struct.unpack("<f", g.read(g.regs()["eax"] + 0x10, 4))[0])

    def toward(self, target, mag: float) -> None:
        """The stick toward a world point (camera-relative; at a player tick)."""
        p = self.body()
        rel = math.radians(xr.wrap(xr.ang_of(target[0] - p[0], target[1] - p[1]) - self.cam_yaw()))
        self.stick = (-math.sin(rel) * mag, math.cos(rel) * mag)

    def use(self, name: str, done, *, n: int = 300, walk_off: int = 0, standoff: float | None = None) -> dict:
        """X on the object ``name`` the way the game's interaction test
        wants it (the body centre within REACH_M of the object's bounding
        sphere, the object faced within 30 deg): optionally walk off it
        first, walk up until 0.3 m inside that range (or stuck), face it,
        press X every 12 ticks until ``done()``.  With ``standoff`` a body
        more than 0.4 m nearer than that to the sphere first backs off to it
        (a keylock X didn't open from inside its sphere: sitting r125-d1's
        death_keylock took from 0.69 m outside it, and not in 540 ticks from
        0.25-0.01 m inside, AZ-498).  A walk-up that stalls (no headway in
        30 ticks) farther than REACH_M outside the sphere gives up there: X
        can't reach from it (sitting r125b, segment 35: 480 ticks of X 1.72 m
        off switch9 while floor 11's enemies took the player's HP, AZ-498)."""
        import numpy as np
        q = self.mesh_live(name)
        c = (q.min(axis=0) + q.max(axis=0)) / 2
        half = float(np.linalg.norm(q.max(axis=0) - q.min(axis=0))) / 2
        st = {"k": 0, "best": 1e9, "best_k": 0}

        def fn(sb, row, rows):
            st["k"] += 1
            k = st["k"]
            if done():
                self.stick = (0.0, 0.0)
                return ["stop"]
            p = self.body()
            if k <= walk_off:
                self.toward((2 * p[0] - c[0], 2 * p[1] - c[1]), 0.5)
                return []
            gap = math.dist(p, c) - half
            if standoff is not None and (st.get("back") or gap < standoff - 0.4):
                st["back"] = gap < standoff               # backing off until the standoff, then on as before
                if st["back"]:
                    self.toward((2 * p[0] - c[0], 2 * p[1] - c[1]), 0.3)
                    st["best"], st["best_k"] = 1e9, k
                    return []
            if gap < st["best"] - 0.05:
                st["best"], st["best_k"] = gap, k
            stuck = k - st["best_k"] > 30
            if stuck and gap > REACH_M:
                st["stalled"] = round(gap, 2)
                self.stick = (0.0, 0.0)
                return ["stop"]
            yaw = math.degrees(struct.unpack("<f", sb.g.read(row["ent"] + YAW, 4))[0])
            face = xr.wrap(xr.ang_of(c[0] - p[0], c[1] - p[1]) - yaw)
            if gap > REACH_M - 0.3 and not stuck and math.dist(p[:2], c[:2]) > 0.6:
                self.toward(c, 0.3)
                return []
            if abs(face) > 20:
                self.toward(c, 0.12)
                return []
            self.stick = (0.0, 0.0)
            return ["down x"] if k % 12 == 0 else (["up x"] if k % 12 == 4 else [])
        meta = self.run(n, on_tick=fn, hook_at=xo.INPUT_BUILD)
        self.stick = (0.0, 0.0)
        p = self.body()
        return {"done": bool(done()), "ticks": st["k"], "gap_m": round(math.dist(p, c) - half, 2), "stop": meta["stop"],
                **({"why": f"the walk-up stalled {st['stalled']} m outside its sphere (X's reach {REACH_M} m)"}
                   if "stalled" in st and not done() else {})}

    def select(self, staff: str | tuple, tries: int = 3) -> bool:
        """The staff's LT combo (the combo is exactly the buttons pressed
        while LT is held), until armor_mgr's staff mask reads it; a tuple
        of elements is that combo (``("water",)``: a single element)."""
        elems = STAFF[staff] if isinstance(staff, str) else tuple(staff)
        want = sum(ELEM[e] for e in elems)
        for _ in range(tries):
            if self.staff_mask() == want:
                return True
            sch, k = {1: "down ltrigger"}, 4
            for e in elems:
                sch[k], sch[k + 3] = f"down {PICK[e]}", f"up {PICK[e]}"
                k += 6
            sch[k + 1] = "up ltrigger"
            self.run(k + 15, stick=(0.0, 0.0), schedule=sch)
        return self.staff_mask() == want

    # ---- the tree song (e6)
    def song_order(self) -> list[str]:
        """The seven tones the data wants: Tone0k_solution_toggle's turnOn
        window (a step curve over WhichWackType_max's index)."""
        by_tone = {v: k for k, v in TONE.items()}
        order = []
        for k in range(1, 8):
            (i, lk, kk, _, _), = [x for x in self.ins(f"Tone0{k}_solution_toggle") if x[4] == "turnOn"]
            cv = link_curve(self.g, i, kk)
            hit = [t for t in range(1, 5) if cv(t * lk.weight) * lk.factor > 0.5]
            order.append(by_tone[hit[0]])
        return order

    def tones(self) -> list[int]:
        return [int(round(self.get(f"Tone0{k}_hit_latch", "output"))) for k in range(1, 8)]

    def song(self, max_hits: int = 30) -> dict:
        """Play the song at the giant crystal (the player near and facing
        it): each tone's staff, A, the tone read back; a wrong tone plays the
        song out with smash hits (after the seventh every latch resets)."""
        order = self.song_order()
        log = []
        for _ in range(max_hits):
            if self.get("SongPuzzleSolved_toggle", "goal") >= 1:
                break
            t = self.tones()
            k = sum(1 for x in t if x >= 1)
            wrong = any(t[j] != TONE[order[j]] for j in range(k))
            staff = "smash" if wrong else order[k]
            ok = self.select(staff)
            self.run(40, stick=(0.0, 0.0), schedule={2: "down a", 6: "up a"})
            log.append((staff, ok, self.tones()))
        return {"solved": self.get("SongPuzzleSolved_toggle", "goal") >= 1, "hits": len(log), "order": order,
                "wrong_tones": sum(1 for s, _, t in log if s == "smash" and t[0] == 0)}

    # ---- aim puzzles: two timers into their windows (e6 spotlights, a6 lasers)
    def window(self, and_name: str) -> dict:
        """{axis input: (source record name, its attribute, lo, hi)} for an
        AND combiner's inputs: where each link's curve is above zero, in the
        source attribute's own units."""
        out = {}
        for i, lk, k, sp, dp in self.ins(and_name):
            cv = link_curve(self.g, i, k)
            xs = [x for x, y, _, _ in cv.keys]
            lo = hi = None
            for a, b in zip(xs, xs[1:]):
                mid = (a + b) / 2
                if cv(mid) * lk.factor > 0:
                    lo = a if lo is None else lo
                    hi = b
            out[dp] = (self.g.names[i], sp, lo / lk.weight, hi / lk.weight)
        return out

    def drive(self, rec: str, attr: str, lo: float, hi: float, axis: str, sign: float = 1.0,
              max_ticks: int = 1500) -> dict:
        """Hold the stick on ``axis`` (x or y) until ``rec.attr`` sits in the
        middle half of (lo, hi): full stick while far, then a release (a
        damper drops at once) and a fine push.  ``sign`` is the attribute's
        response to a positive stick."""
        target, tol = (lo + hi) / 2, (hi - lo) / 4
        st = {"phase": "fast", "brake": 0, "n": 0}

        def fn(sb, row, rows):
            st["n"] += 1
            e = (target - self.get(rec, attr)) * sign
            if abs(e) < tol and st["phase"] != "fast":
                self.stick = (0.0, 0.0)
                return ["stop"]
            if st["phase"] == "fast" and abs(e) <= 0.12 * (hi - lo) / 0.04:
                st["phase"], st["brake"] = "brake", 5
            if st["phase"] == "brake":
                self.stick = (0.0, 0.0)
                st["brake"] -= 1
                st["phase"] = "fine" if st["brake"] <= 0 else "brake"
                return []
            v = math.copysign(1.0 if st["phase"] == "fast" else 0.15, e)
            self.stick = (v, 0.0) if axis == "x" else (0.0, v)
            return []
        self.run(max_ticks, on_tick=fn)
        self.run(8, stick=(0.0, 0.0))
        cur = self.get(rec, attr)
        return {"rec": rec, "in": lo < cur < hi, "ticks": st["n"]}

    # ---- the hose (w2)
    HOSE_FIRES = ("OpenNCloseToggle3", "OpenNCloseToggle11", "OpenNCloseToggle12", "OpenNCloseToggle13",
                  "OpenNCloseToggle14", "OpenNCloseToggle15")
    HOSE_JOY = "HoseStuff:PublicJoystickShape"
    # the moves that put the six fires out in one round (sitting r18f, USA; found by cooled sweeps, each followed by a
    # hold): a slow stream over x 0.36-0.46 at y 0.75 puts out the far fires 12, 15 and 16 (toggles 11, 14, 15), a sweep
    # at y 0.82 fires 4 and 15 (3, 14), a sweep at y 0.95 out to x -0.1 the near fires 13 and 14 (12, 13); the far
    # ones go first (a near sweep first left them dry), and the last hold keeps them out
    HOSE_PLAN = (("hold", 0.75, 0.36, 0.46, 90), ("sweep", 0.82, 0.19, 0.50, 30), ("sweep", 0.95, 0.50, -0.1, 40),
                 ("hold", 0.75, 0.46, 0.38, 150))

    def hose_on(self) -> dict:
        """X at the console (the player near it): HoseStuff:toggle10 latches, keyToggle runs the water.  No walk-off
        (AZ-394): the console's platform is small, and sitting r18o's 20-tick walk-off took the player off it."""
        return self.use("LightShape", lambda: self.get("HoseStuff:toggle10", "goal") >= 1, walk_off=0)

    def hose_engage(self) -> dict:
        """X at the joystick, on the fountain path's narrow tip: no walk-off either (AZ-394; sitting r18o3)."""
        return self.use(self.HOSE_JOY, lambda: self.get(self.HOSE_JOY, "joystickOn") >= 1, walk_off=0)

    def hose_steers(self) -> bool:
        """Is the stick turning the nozzle (the joystick on and the player
        still on it)?  A short push must move damper2."""
        if self.get(self.HOSE_JOY, "joystickOn") < 1:
            return False
        a = self.get("HoseStuff:damper2", "output")
        self.run(6, stick=(-0.5 if a > -10 else 0.5, 1.0))
        return abs(self.get("HoseStuff:damper2", "output") - a) > 3.0

    def _fires(self) -> dict[str, float]:
        return {f: self.get(f, "output") for f in self.HOSE_FIRES}

    def _cool(self, stick, limit: int = 300) -> None:
        """Hold the stream off the machine until every fire is back."""
        self.run(limit, stick=stick,
                 on_tick=lambda sb, row, rows: ["stop"] if max(self._fires().values()) < 0.02 else [])

    def hose_solve(self, plan=None, rounds: int = 6) -> dict:
        """:data:`HOSE_PLAN`'s holds and sweeps (kind, y, x from, x to,
        ticks), round after round, until hosetoggle latches (all six fires
        out at once).  The water lands 3-5 s after the aim and a fire stays
        out about 8 s, so a round's last hold refreshes its first while the
        sweeps' fires are still out.  Each round starts with every fire
        burning (a cooled start: back-to-back rounds lit only the two
        nearest)."""
        plan = plan or self.HOSE_PLAN
        latched = lambda: self.get("HoseStuff:hosetoggle", "goal") >= 1   # noqa: E731
        self.hose_log = []
        for c in range(rounds):
            if not self.hose_steers():
                self.hose_engage()
            self._cool((-1.0, plan[0][1]))     # a round starts with every fire burning: near sinks lit for long
            lit: set[str] = set()             # rounds left the far ones dry (sitting r18f)
            for kind, y, a, b, ticks in plan:
                self.run(8, stick=(a, y))      # the nozzle onto the move's start (the dampers turn 60 deg/s)
                st = {"k": 0}

                def fn(sb, row, rows, y=y, a=a, b=b, ticks=ticks):
                    st["k"] += 1
                    self.stick = (a + (b - a) * min(1.0, st["k"] / ticks), y)
                    lit.update(f for f, v in self._fires().items() if v > 0.02)
                    return ["stop"] if st["k"] >= ticks or latched() else []
                self.run(ticks + 2, stick=(a, y), on_tick=fn)
                if latched():
                    break
            self.hose_log.append(sorted(lit))
            if latched():
                return {"solved": True, "rounds": c + 1}
        return {"solved": False, "rounds": rounds}

    def hose(self) -> dict:
        """The whole hose, the player near the console: X there (the water
        on), X at the joystick (the player beside or on it), the six fires
        (:meth:`hose_solve`), and off the joystick (X)."""
        r = {"console": self.hose_on(), "joystick": self.hose_engage()}
        r["solve"] = self.hose_solve()
        self.run(12, stick=(0.0, 0.0), schedule={2: "down x", 6: "up x"})
        r["solved"] = r["solve"]["solved"]
        return r

    def drive_rate(self, rec: str, attr: str, lo: float, hi: float, axis: str, max_ticks: int = 900) -> dict:
        """As :meth:`drive` for an aim whose stick sets its rate with no
        damper (a6's lasers): the response measured over a short push, then
        a proportional stick that closes in about ten ticks."""
        target, tol = (lo + hi) / 2, (hi - lo) / 4
        gain = 0.0
        for push in (0.5, -0.5):                           # one way may sit at the timer's end
            v0 = self.get(rec, attr)
            self.run(4, stick=(push, 0.0) if axis == "x" else (0.0, push))
            self.run(2, stick=(0.0, 0.0))
            gain = (self.get(rec, attr) - v0) / (4 * push)  # the attribute per tick per unit of stick
            if abs(gain) > 1e-6:
                break
        if abs(gain) < 1e-6:
            return {"rec": rec, "in": False, "why": "the stick moved nothing (is the joystick engaged?)"}
        st = {"n": 0}

        def fn(sb, row, rows):
            st["n"] += 1
            e = target - self.get(rec, attr)
            if abs(e) < tol:
                self.stick = (0.0, 0.0)
                return ["stop"]
            v = max(-1.0, min(1.0, e / gain / 10.0))
            v = math.copysign(max(abs(v), 0.02), v)
            self.stick = (v, 0.0) if axis == "x" else (0.0, v)
            return []
        self.run(max_ticks, on_tick=fn)
        self.run(6, stick=(0.0, 0.0))
        cur = self.get(rec, attr)
        return {"rec": rec, "in": lo < cur < hi, "ticks": st["n"]}

    # ---- the lasers (a6)
    LASERS = {"red": ("RedAngleCheck_andCombiner", "AirSwitch:lightShape"),
              "green": ("GreenAngleCheck_andCombiner", "AirSwitch2:lightShape"),
              "blue": ("BlueAngleCheck_andCombiner", "AirSwitch1:lightShape")}

    def laser(self, colour: str) -> dict:
        """One laser onto its receptacle, the player at its mirror's switch:
        X engages the joystick (live once its keylock has its key), the stick
        x turns the mirror's Z rotation and y its X rotation into the
        AngleCheck's windows."""
        check, joy = self.LASERS[colour]
        r = {"engage": self.use(joy, lambda: self.get(joy, "joystickOn") >= 1, walk_off=0)}
        if not r["engage"]["done"]:
            return {"lit": False, **r}
        w = self.window(check)
        for plug, axis in (("inputs[0]", "x"), ("inputs[1]", "y")):
            rec, attr, lo, hi = w[plug]
            r[rec] = self.drive_rate(rec, attr, lo, hi, axis)
        self.run(30, stick=(0.0, 0.0))
        r["lit"] = self.get(check, "output") > 0
        return r

    # ---- live geometry (moving rigs: a5's smokestacks, life's cores)
    def xform_live(self, name) -> list[float]:
        """A transform's translate, rotate and scale as the links drive them
        this frame: the level's values, each driven plug replaced by its
        link's value from the source's live attribute (a transform's own
        node keeps no attribute block where ``attrs`` reads one: measured,
        sitting r18f)."""
        j = self.find(name)
        names = self.schema.types[self.g.types[j]].attrs
        a = list(self.g.attrs(j))
        for i, lk, k, sp, dp in self.ins(j):
            if dp in names[1:10]:
                try:
                    src = (self.xform_live(i)[self.schema.types[self.g.types[i]].attrs.index(sp)]
                           if self.schema.is_a(self.g.types[i], "transform") else self.get(i, sp))
                except OSError:          # a source whose node keeps no readable block: the level's value stays
                    self.unread = getattr(self, "unread", set()) | {self.g.types[i]}
                    continue
                a[names.index(dp)] = link_value(link_curve(self.g, i, k), src, lk.weight, lk.factor)
        return a

    def _xf(self, j: int) -> dict:
        if not hasattr(self, "_xfc"):
            self._xfc = {}
        if j not in self._xfc:
            self._xfc[j] = self.g.xform_fields(j)
        return self._xfc[j]

    def live_world(self, name):
        """A record's world matrix with every ancestor transform's live
        translate, rotate and scale (:meth:`xform_live`; their other fields
        from the level), as ``nodes.Graph.world`` composes them (in memory
        only)."""
        g, i = self.g, self.find(name)
        m = N.IDENTITY
        for j in [i, *g.ancestors(i)][::-1]:
            if not self.schema.is_a(g.types[j], "transform"):
                continue
            x, a = self._xf(j), self.xform_live(j)
            t, r, s = a[1:4], a[4:7], a[7:10]
            sp, spt, rp, rpt = x["sp"], x["spt"], x["rp"], x["rpt"]
            loc = N.translate(t[0] + rpt[0] + rp[0], t[1] + rpt[1] + rp[1], t[2] + rpt[2] + rp[2])
            loc = N.mat_mul(loc, self.schema.rotation(*r, x["order"]))
            loc = N.mat_mul(loc, N.translate(spt[0] + sp[0] - rp[0], spt[1] + sp[1] - rp[1], spt[2] + sp[2] - rp[2]))
            loc = N.mat_mul(loc, N.scale(*s))
            loc = N.mat_mul(loc, N.translate(-sp[0], -sp[1], -sp[2]))
            if x["mode"] == 1:
                anchor = tuple(t[k] + rp[k] for k in range(3))
                q = N.apply(m, anchor)
                m = N.translate(q[0] - anchor[0], q[1] - anchor[1], q[2] - anchor[2])
            m = N.mat_mul(m, loc)
        return m

    # ---- the cannon (a5)
    CANNON_JOY = "Active_switchShape"
    CANNON_SHOT = "pEmitterShape1"      # under Barrel_Tilt: 25 m/s along its local -y (velocityBaseY -25)

    def stacks(self) -> list[str]:
        """The nine smokestacks' ice sinks (``Sub_Main*:Smokestack*:Public_Ice_sinkShape``)."""
        return sorted(n for n in self.by if n.endswith(":Public_Ice_sinkShape") and n.startswith("Sub_Main"))

    def stack_iced(self, sink: str) -> bool:
        """True once the stack's ice is broken (its Public_Ice_toggle latched)."""
        return self.get(sink.replace("Public_Ice_sinkShape", "Public_Ice_toggle"), "goal") >= 1

    def _shot(self) -> int:
        """The cannon's shot emitter: the pEmitterShape1 under Barrel_Tilt (a5 has four of that name)."""
        return next(i for i in self.by[self.CANNON_SHOT]
                    if "Barrel_Tilt" in [self.g.names[a] for a in self.g.ancestors(i)])

    def _muzzle(self):
        m = self.live_world(self._shot())
        o = (m[0][3], m[1][3], m[2][3])
        d = (-m[0][1], -m[1][1], -m[2][1])
        n = math.sqrt(sum(c * c for c in d)) or 1.0
        return o, tuple(c / n for c in d)

    def _sink_at(self, sink: str):
        return tuple(float(v) for v in self._sink_world(self.find(sink)))

    def cannon(self, max_ticks: int = 9000, speed: float = 25.0, drop: float = 0.0) -> dict:
        """Break the nine stacks' ice (the player engaged at the cannon): pick
        the unbroken stack whose lead point is nearest the barrel's aim, turn
        the barrel onto it (yaw from the stick's x, pitch from y, gains
        measured on the way) and hold it there while the cannon fires itself
        (every 2.2 s); a stack the aim holds for 3 shots without a hit gets
        its pitch raised a degree (the shot falls; ``drop`` adds a fixed
        fall in m/s^2)."""
        st = {"k": 0, "target": None, "on_since": None, "prev": {}, "offset": {}, "hits": 0}
        sinks = self.stacks()

        def yaw_pitch():
            _, d = self._muzzle()
            return math.degrees(math.atan2(d[1], d[0])), math.degrees(math.asin(max(-1.0, min(1.0, d[2]))))
        y0, p0 = yaw_pitch()
        self.run(10, stick=(0.5, 0.0))
        y1, _ = yaw_pitch()
        self.run(10, stick=(0.0, 0.5))
        _, p1 = yaw_pitch()
        self.run(4, stick=(0.0, 0.0))
        sgn_x = 1.0 if xr.wrap(y1 - y0) > 0 else -1.0        # the stick's x turns the barrel this way
        sgn_y = 1.0 if p1 - p0 > 0 else -1.0

        def lead(sink, o):
            p = self._sink_at(sink)
            q = st["prev"].get(sink)
            st["prev"][sink] = p
            v = tuple((p[i] - q[i]) * 30.0 for i in range(3)) if q else (0.0, 0.0, 0.0)
            t = math.dist(o, p) / speed
            return tuple(p[i] + v[i] * t for i in range(3)), t

        def fn(sb, row, rows):
            st["k"] += 1
            left = [s for s in sinks if not self.stack_iced(s)]
            if not left:
                self.stick = (0.0, 0.0)
                return ["stop"]
            o, d = self._muzzle()
            aims = {}
            for s in left:
                p, t = lead(s, o)
                off = st["offset"].get(s, 0.0)
                w = (p[0] - o[0], p[1] - o[1], p[2] - o[2] + off + drop * t * t / 2)
                aims[s] = w
            if st["target"] not in left:
                st["target"] = min(left, key=lambda s: _angle(d, aims[s]))
                st["on_since"] = None
            w = aims[st["target"]]
            yaw_e = xr.wrap(math.degrees(math.atan2(w[1], w[0]) - math.atan2(d[1], d[0])))
            pit_e = math.degrees(math.atan2(w[2], math.hypot(w[0], w[1])) - math.asin(max(-1.0, min(1.0, d[2]))))
            if abs(yaw_e) < 1.0 and abs(pit_e) < 1.0:
                st["on_since"] = st["on_since"] or st["k"]
                if st["k"] - st["on_since"] > 200:      # three shots on it and no hit: raise the aim a step
                    st["offset"][st["target"]] = st["offset"].get(st["target"], 0.0) + 1.0
                    st["on_since"] = None
            sx = max(-1.0, min(1.0, sgn_x * yaw_e / 20.0))
            sy = max(-1.0, min(1.0, sgn_y * pit_e / 20.0))
            self.stick = (sx, sy)
            return []
        self.run(max_ticks, on_tick=fn)
        self.stick = (0.0, 0.0)
        return {"broken": sum(1 for s in sinks if self.stack_iced(s)), "of": len(sinks), "ticks": st["k"],
                "offsets": {s.split(":")[0] + ":" + s.split(":")[1]: v for s, v in st["offset"].items()}}


    # ---- the periscope's torpedo (w1)
    TORPEDO_JOY = "pCubeShape7"         # live once the station's overlords are dead and the player stands on pCubeShape356

    def torpedo_window(self) -> tuple[float, float, float]:
        """(lo, hi, cycle) of PeriscopeTimer's time while the periscope points
        at the tower: the timer turns the periscope's Camera (its rotateZ
        link) and StatueRotToggle's turnOn link reads that rotation in
        degrees through a curve that repeats past its keys (infinity mode 2,
        taken as a cycle; the solver checks turnOn live)."""
        ti = self.find("PeriscopeTimer")
        (cam, k1, lk1), = [(lk.dst, k, lk) for k, lk in enumerate(self.g.links(ti))
                           if self.g.plug_name(lk.dst, lk.dst_plug) == "rotateZ"]
        (_, lk2, k2, _, _), = [x for x in self.ins("StatueRotToggle") if x[0] == cam and x[4] == "turnOn"]
        cv1, cv2 = link_curve(self.g, ti, k1), link_curve(self.g, cam, k2)
        x0, xl = cv2.keys[0][0], cv2.keys[-1][0]
        cycle = self.g.attr_named(ti, "stopTime")
        on = []
        for k in range(40000):
            t = cycle * k / 40000
            x = link_value(cv1, t, lk1.weight, lk1.factor) * lk2.weight
            if cv2(x0 + (x - x0) % (xl - x0)) * lk2.factor > 0:
                on.append(t)
        if not on:
            raise SystemExit("w1: StatueRotToggle is on at no periscope heading")
        return min(on), max(on), cycle

    def torpedo(self, tries: int = 3, aim_ticks: int = 1500) -> dict:
        """Topple the tower (the player at the periscope, its joystick live):
        X on the joystick; the stick's x turns the periscope (PeriscopeTimer's
        rate; the gain and its sign measured with a short push) onto the
        middle of :meth:`torpedo_window` by the shorter way round the cycle,
        held until StatueRotToggle reads on; X again lets go, which launches
        the torpedo; then the flight, the blast and StatueTimer are watched
        until the tower is down (StatueToggle latched, the wall's gameSolid
        off).  A miss waits for ExplodeTimer's reset and fires again."""
        joy = self.TORPEDO_JOY
        lo, hi, cycle = self.torpedo_window()
        target, tol = (lo + hi) / 2, (hi - lo) / 4
        down = lambda: self.get("StatueToggle", "goal") >= 1   # noqa: E731
        engaged = lambda: self.get(joy, "joystickOn") >= 1   # noqa: E731
        log = []
        for _ in range(tries):
            if down():
                break
            # a torpedo still out (LaunchToggle on) or a blast not yet reset: wait for ExplodeTimer's reset (24 s)
            self.run(900, stick=(0.0, 0.0),
                     on_tick=lambda sb, row, rows: ["stop"] if self.get("LaunchToggle", "output") < 0.5 else [])
            row = {"engage": self.use(joy, engaged, walk_off=0)}
            if not engaged():
                log.append(row)
                continue
            t0 = self.get("PeriscopeTimer", "currentTime")
            self.run(6, stick=(0.5, 0.0))
            self.run(2, stick=(0.0, 0.0))
            gain = ((self.get("PeriscopeTimer", "currentTime") - t0 + cycle / 2) % cycle - cycle / 2) / (6 * 0.5)
            if abs(gain) < 1e-6:
                log.append(dict(row, why="the stick turned nothing"))
                continue
            st = {"n": 0, "held": 0}

            def aim(sb, rw, rows):
                st["n"] += 1
                e = (target - self.get("PeriscopeTimer", "currentTime") + cycle / 2) % cycle - cycle / 2
                if abs(e) < tol and self.get("StatueRotToggle", "turnOn") > 0:
                    self.stick = (0.0, 0.0)
                    st["held"] += 1
                    return ["stop"] if st["held"] >= 8 else []
                st["held"] = 0
                v = max(-1.0, min(1.0, e / gain / 8.0))          # closes in about eight ticks
                self.stick = (math.copysign(max(abs(v), 0.03), v), 0.0)
                return []
            self.run(aim_ticks, on_tick=aim)
            row.update(aim_ticks=st["n"], aimed=self.get("StatueRotToggle", "turnOn") > 0)
            self.run(12, stick=(0.0, 0.0), schedule={2: "down x", 6: "up x"})   # off the joystick: the launch
            seen = {"launch": False, "blast": False}

            def watch(sb, rw, rows):
                seen["launch"] |= self.get("LaunchToggle", "output") >= 1
                seen["blast"] |= self.get("ExplodeToggle", "output") >= 1
                if down() and self.get("StatueTimer", "currentTime") >= 4.0:
                    return ["stop"]
                return ["stop"] if seen["launch"] and self.get("LaunchToggle", "output") < 0.5 else []
            self.run(1200, stick=(0.0, 0.0), on_tick=watch)
            log.append(dict(row, **seen, toppled=down()))
        self.run(60, stick=(0.0, 0.0))
        return {"toppled": down(), "attempts": len(log), "log": log, "window_timer": [round(lo, 4), round(hi, 4)],
                "statue_timer": round(self.get("StatueTimer", "currentTime"), 2),
                "wall_solid": {n: self.get(n, "gameSolid") for n in ("pPlaneShape14", "Rolling_rock1Shape",
                                                                      "Rolling_rock3Shape")}}

    # ---- the spotlights (e6)
    PANELS ={"red": ("RedPanel_Toggle4", "RedPanel_Toggle5", "RedPanel_Toggle6"),
              "blue": ("BluePanel_Toggle7", "BluePanel_Toggle8", "BluePanel_Toggle9")}

    def panel_ways(self, panel: str) -> list[dict]:
        """Each way to light ``panel``: its AND combiner, the two aim timers
        with their windows, the light's joystick and the pad that lives it
        (the pad's touch -> xorCombiner -> Mirror_Toggle -> joystickEnable)."""
        ways = []
        for orc, *_ in [x for x in self.ins(panel) if x[4] == "turnOn"]:
            srcs = self.ins(orc)
            ands = [orc] if any("Rot" in self.g.names[i] for i, *_ in srcs) else [i for i, *_ in srcs]
            for a in ands:
                w = {"and": self.g.names[a], "timers": self.window(a)}
                y = next(v for v in w["timers"].values() if "RotY" in v[0])
                joys = set()
                for d, *_r, dp in self.ins(y[0]):
                    for c, *_r2, dp2 in self.ins(d):
                        for p, _lk, _k, sp, _dp in self.ins(c):
                            if sp.startswith("joystick"):
                                joys.add(self.g.names[p])
                w["light"] = sorted(j for j in joys if j.startswith("Light"))[0]
                for mt, _lk, _k, _sp, dp in self.ins(w["light"]):
                    if dp == "joystickEnable":
                        for x, *_ in self.ins(mt):
                            for p, _lk2, _k2, sp, _dp2 in self.ins(x):
                                if sp == "touch":
                                    w["pad"] = self.g.names[p]
                ways.append(w)
        return ways

    def plate(self, light: str) -> str:
        """A spotlight's second joystick plate (pCubeShape454 ... jShape): the
        other platform its pad's Mirror_Toggle enables; either one aims it."""
        mt = next(i for i, *_r, dp in self.ins(light) if dp == "joystickEnable")
        return next(self.g.names[lk.dst] for lk in self.g.links(mt)
                    if self.g.plug_name(lk.dst, lk.dst_plug) == "joystickEnable" and self.g.names[lk.dst] != light)

    def engaged(self, light: str) -> bool:
        return self.get(light, "joystickOn") >= 1 or self.get(self.plate(light), "joystickOn") >= 1

    def engage_light(self, light: str, n: int = 200) -> bool:
        """X on a spotlight's joystick (the player on its pad), walked up to
        where it stands now (:meth:`use` on its live mesh), on the light or
        its plate: once its pad's mirror toggle runs, the joystick rises
        1.5 m (Mirror_Joystck_Timer -> Joystick.translateZ), and X from the
        pad at its old height missed it (AZ-355, sitting r18i)."""
        for name in (light, self.plate(light)):
            if self.engaged(light) or self.use(name, lambda: self.engaged(light), n=n)["done"]:
                return True
        return False

    def release_light(self, light: str, tries: int = 4) -> bool:
        """X until neither of the spotlight's joysticks is held."""
        for _ in range(tries):
            if not self.engaged(light):
                return True
            self.run(12, stick=(0.0, 0.0), schedule={2: "down x", 6: "up x"})
            self.run(10, stick=(0.0, 0.0))
        return not self.engaged(light)

    def aim_light(self, way: dict) -> dict:
        """One spotlight (the player on its pad) onto one orb: X, then its
        RotY timer (the stick's y) and RotZ timer (x) into the way's
        windows, then off the joystick; the panel's toggle is read after it
        ramps (4 s)."""
        r = {"light": way["light"], "on": self.engage_light(way["light"])}
        if not r["on"]:
            return r
        for plug, (rec, attr, lo, hi) in sorted(way["timers"].items(), key=lambda kv: "RotZ" in kv[1][0]):
            r[rec] = self.drive(rec, attr, lo, hi, "y" if "RotY" in rec else "x")
        self.run(150, stick=(0.0, 0.0))
        r["released"] = self.release_light(way["light"])
        self.run(20, stick=(0.0, 0.0))
        r["lit"] = self.get(way["panel"], "goal") >= 1 if "panel" in way else None
        return r

    # The owner's order (Step R1.8i, AZ-355; draft/authoring/e6.toml's e6.blue_machine.on): red first from the lower
    # ring (Light2, 4, 6), the red lift up, upper-ring lights onto red orbs and Light3 onto blue 9, back down, Light2
    # and Light6 onto blue: both machines on, every orb lit by one light and red 4 and red 6 by two on the way.
    SPOTLIGHT_ORDER = (("RedPanel_Toggle4", "Light2Shape"), ("RedPanel_Toggle5", "Light4Shape"),
                       ("RedPanel_Toggle6", "Light6Shape"), "up",
                       ("RedPanel_Toggle4", "Light5Shape"), ("RedPanel_Toggle6", "Light1Shape"),
                       ("BluePanel_Toggle9", "Light3Shape"), "down",
                       ("BluePanel_Toggle8", "Light2Shape"), ("BluePanel_Toggle7", "Light6Shape"))
    RED_LIFT = 1726           # Red_Machine's Public_FieldShape1 (pushZ 4 while RedOnToggle is on, 31 m tall)
    VENT = "pCubeShape63"     # the upper ring's steam vent (springboard 17.5, autoSpring) beside the blue beam
    BEAM = 2182               # the blue beam's Public_FieldShape1 (its push carries a body along it)

    def machines(self) -> dict:
        return {"red": self.get("RedOnToggle", "goal") >= 1, "blue": self.get("BlueOnToggle", "goal") >= 1}

    def spotlights(self, to_pad, up=None, down=None) -> dict:
        """Both machines on in the owner's order (:data:`SPOTLIGHT_ORDER`).
        ``to_pad(pad, light)`` brings the player onto a spotlight's pad
        facing its light (a sitting's walk or R6; sitting r18i lost a run to
        a death on a pad placed facing elsewhere, cause not traced),
        ``up()`` up to the upper ring (default: nothing, the sitting's
        ``to_pad`` gets there) and ``down()`` back down; each aim is
        :meth:`aim_light`. Returns each step and the machines after it."""
        steps = []
        for step in self.SPOTLIGHT_ORDER:
            if isinstance(step, str):
                f = up if step == "up" else down
                steps.append((step, f() if f else None, self.machines()))
                continue
            panel, light = step
            way = next(dict(w, panel=panel) for w in self.panel_ways(panel) if w["light"] == light)
            to_pad(way["pad"], light)
            self.run(20, stick=(0.0, 0.0))
            steps.append((f"{light}->{panel}", self.aim_light(way), self.machines()))
        return {"solved": self.machines() == {"red": True, "blue": True}, "steps": steps}

    def lift(self, field: int = RED_LIFT, to=None, max_ticks: int = 1000) -> dict:
        """The red lift from its floor (the player on it): a jump into the
        field, then no input while it lifts; at the top, the stick toward
        ``to`` (a floor point of the upper ring the sitting picks; in
        memory) with flaps, until the feet are on it. Returns the rise."""
        q = self.mesh(field)
        hi = float(q[:, 2].max())
        st = {"k": 0, "z0": None, "zmax": -1e9, "still": 0, "zp": None, "top": None, "taps": 0}

        def fn(sb, row, rows):
            st["k"] += 1
            p = self.body()
            z = p[2]
            st["z0"] = z if st["z0"] is None else st["z0"]
            st["zmax"] = max(st["zmax"], z)
            if st["top"] is None:
                if st["zp"] is not None and st["k"] > 30:
                    st["still"] = st["still"] + 1 if abs(z - st["zp"]) < 0.01 else 0
                st["zp"] = z
                self.stick = (0.0, 0.0)
                if z - 1.0 > hi - 0.5 or st["still"] > 20:
                    if to is None:
                        return ["stop"]
                    st["top"] = st["k"]
                return {2: ["down y"], 8: ["up y"]}.get(st["k"], [])
            self.toward(to, 1.0)
            k = st["k"] - st["top"]
            if (math.dist(p[:2], to[:2]) < 0.8 and abs(z - 1.0 - to[2]) < 0.6) or k > 240:
                return ["stop"]
            if st["taps"] < 4 and k % 12 == 0:
                st["taps"] += 1
                return ["down y"]
            return ["up y"] if k % 12 == 4 else []
        self.run(max_ticks, on_tick=fn, hook_at=xo.INPUT_BUILD)
        self.run(30, stick=(0.0, 0.0))
        return {"rise_m": round(st["zmax"] - st["z0"], 1), "ticks": st["k"]}

    def vent_beam(self, frag: str = "e6/g0/r2755", max_ticks: int = 3200, each=None) -> dict:
        """From beside the steam vent (both machines on, the player on the
        upper ring): walk onto the vent, steer into the beam's field while
        rising, let it carry the player along the beam, and within 18 m of
        frag_earth_3 a jump and two flaps toward it. ``each()`` runs every 5
        ticks (a kit hold). Stops when the inventory changes."""
        import numpy as np
        F = self.mesh(self.BEAM)
        fc = F.mean(axis=0)
        ax = np.linalg.svd(F - fc)[2][0]
        fragp = np.array(self.geo.rec_points(frag)[0][0])
        ax = ax if np.dot(fragp - fc, ax) > 0 else -ax
        V = self.mesh(self.VENT)
        vc, vtop = V.mean(axis=0), float(V[:, 2].max())
        r_field = float(np.max(np.linalg.norm((F - fc) - np.outer((F - fc) @ ax, ax), axis=1)))
        def frags():
            inv = recipes.inventory(self.sb.read(recipes.chain(self.sb.read_u32)["inv"], recipes.INV_SAVED))
            return {k: v for k, v in inv.items() if k.startswith("fg")}
        frags0 = frags()
        st = {"k": 0, "phase": "walk", "zmax": -1e9, "rise_k": None, "in_k": None, "jk": None, "dmin": 1e9}

        def fn(sb, row, rows):
            st["k"] += 1
            p = np.array(self.body())
            st["zmax"] = max(st["zmax"], p[2] - 1.0 - vtop)
            d = float(np.linalg.norm(p - fragp))
            st["dmin"] = min(st["dmin"], d)
            t = float(np.dot(p - fc, ax))
            off = float(np.linalg.norm((p - fc) - t * ax))
            if st["k"] % 5 == 0:
                if each:
                    each()
                if frags() != frags0:
                    return ["stop"]
            if st["phase"] == "walk":
                self.toward(vc, 1.0)
                if p[2] - 1.0 - vtop > 2.0:
                    st["phase"], st["rise_k"] = "rise", st["k"]
                return [] if st["k"] < 300 else ["stop"]
            if st["phase"] == "rise":
                self.toward(fc + ax * t, 1.0)
                if off < 0.6 * r_field:
                    st["phase"], st["in_k"] = "ride", st["k"]
                return [] if st["k"] - st["rise_k"] < 240 else ["stop"]
            if d > 18.0:
                self.toward(fc + ax * (t + 10.0), 0.5)
                return [] if st["k"] - st["in_k"] < 2400 else ["stop"]
            self.toward(fragp, 1.0)
            if st["jk"] is None:
                st["jk"] = st["k"]
                return ["down y"]
            k = st["k"] - st["jk"]
            return {6: ["up y"], 14: ["down y"], 18: ["up y"], 26: ["down y"], 30: ["up y"]}.get(k, [] if k < 240 else ["stop"])
        self.run(max_ticks, on_tick=fn, hook_at=xo.INPUT_BUILD)
        self.run(30, stick=(0.0, 0.0))
        return {"launched": st["rise_k"] is not None, "apex_over_vent_m": round(st["zmax"], 1),
                "in_beam": st["in_k"] is not None, "dmin_frag_m": round(st["dmin"], 1), "ticks": st["k"],
                "fragments_gained": sorted(k for k, v in frags().items() if v > frags0[k])}

    # ---- the filament cores (life)
    def _sink_world(self, i: int):
        """A particle sink's centre: its parent's live world matrix times its own localPosition (pSink and
        pBoxSink are no transforms; s1-s20 sit 58 m out, on the ball's sphere)."""
        import numpy as np
        a = self.attrs(i)
        m = np.array(self.live_world(self.g.parent(i)))
        return (m @ np.array([a["localPositionX"], a["localPositionY"], a["localPositionZ"], 1.0]))[:3]

    def cores(self, max_ticks: int = 9000, gain: float = 0.2) -> dict:
        """Steer the pilot ball through the 20 filament cores (the player
        engaged at the final joystick).  In FlybyCamera's frame the ball
        (``particles``) runs round the x axis on a 58 m sphere, its longitude
        driven by the speed timer (the stick's y: 0.5-2.5x) and its x by the
        steering timer (the stick's x sets its rate); the cores (pSinks
        s1-s20, 1.5 m sinks) sit on the same sphere, some still, some
        carried round by the spinning rings, often faster than the ball and
        the other way.  Every 5 ticks each unlit core's longitude and x rates
        are measured, the meeting time with the ball worked out, and the
        soonest meeting the steering can reach is the target; the stick's x
        drives the ball's x onto the core's x at that meeting (a
        proportional controller, its sign measured first).  A crash (a
        stabilizer stream) resets every core, greys the joystick 5 s and
        ends the joystick session: the solver waits, presses X again and goes
        on."""
        import numpy as np
        ball = self.g.parent(self.find("pSystemShape8"))
        frame = self.find("FlybyCamera")
        sinks = {k: self.find(f"s{k}") for k in range(1, 21)}
        done = lambda: self.get("BeamToggle", "goal") >= 1   # noqa: E731
        lvl = self.sb.read(self.pd, 0x50).split(b"\0")[0]
        joys = [i for i, n in enumerate(self.g.names) if n in ("BlockerShape", "Body1Shape", "LensShape")
                and "EnergySwitch" in [self.g.names[a] for a in self.g.ancestors(i)]]
        on = lambda: max(self.get(j, "joystickOn") for j in joys) >= 1   # noqa: E731
        body1 = next(j for j in joys if self.g.names[j] == "Body1Shape")
        engages = 0
        if not on():
            engages += 1
            if not self.use(body1, on, n=200)["done"]:
                return {"won": False, "ticks": 0, "crashes": 0, "most_lit": 0, "engages": engages}

        def local(pw):
            m = np.linalg.inv(np.array(self.live_world(frame)))
            return (m @ np.append(pw, 1.0))[:3]

        def bpos():
            m = self.live_world(ball)
            return local(np.array([m[0][3], m[1][3], m[2][3]]))

        def lon(p):
            return math.degrees(math.atan2(p[1], p[2]))
        b0 = bpos()
        self.run(6, stick=(0.0, 0.0))
        b1 = bpos()
        sense = 1.0 if xr.wrap(lon(b1) - lon(b0)) > 0 else -1.0
        self.run(10, stick=(0.8, 0.0))
        b2 = bpos()
        self.run(4, stick=(0.0, 0.0))
        lat_sign = 1.0 if b2[0] > b1[0] else -1.0
        st = {"k": 0, "crashes": 0, "in_crash": False, "lit_max": 0, "target": None, "cores": {}, "ball": None,
              "aim_x": None}

        def survey(b):
            """Each unlit core: (x, lon, x rate, lon rate) a tick, from the last survey."""
            now = {}
            for k, i in sinks.items():
                if self.get(f"t{k}", "goal") >= 1:
                    continue
                c = local(self._sink_world(i))
                x, la = float(c[0]), lon(c)
                old = st["cores"].get(k)
                if old:
                    now[k] = (x, la, (x - old[0]) / 5.0, xr.wrap(la - old[1]) / 5.0)
                else:
                    now[k] = (x, la, 0.0, 0.0)
            st["cores"] = now
            st["lit_max"] = max(st["lit_max"], 20 - len(now))

        def fn(sb, row, rows):
            st["k"] += 1
            if done() or (st["k"] % 30 == 0 and self.sb.read(self.pd, 0x50).split(b"\0")[0] != lvl):
                self.stick = (0.0, 0.0)
                return ["stop"]
            if self.get("CrashToggle", "goal") >= 1:
                st["crashes"] += 0 if st["in_crash"] else 1
                st["in_crash"], st["cores"] = True, {}
                self.stick = (0.0, 0.0)
                return []
            if st["k"] % 10 == 0 and not on():          # a crash ends the joystick session: X again
                st["in_crash"] = False
                self.stick = (0.0, 0.0)
                return ["stop"]
            st["in_crash"] = False
            b = bpos()
            wb = xr.wrap(lon(b) - lon(st["ball"])) if st["ball"] is not None else 0.37 * sense
            st["ball"] = b
            if st["k"] % 5 == 0 or not st["cores"]:
                survey(b)
                best = None
                for k, (x, la, vx, vl) in st["cores"].items():
                    rel = (wb - vl) * sense                       # closing rate in the ball's direction, deg a tick
                    gap = (xr.wrap(la - lon(b)) * sense) % 360.0
                    if rel <= 0.05:
                        continue
                    t = gap / rel
                    xp = x + vx * t
                    reach = 0.45 * t + 1.0                        # the steering's lateral reach, m
                    if abs(xp - b[0]) <= reach and (best is None or t < best[0]):
                        best = (t, k, xp)
                st["target"], st["aim_x"] = (best[1], best[2]) if best else (None, None)
            if st["aim_x"] is None:
                self.stick = (0.0, 0.0)
                return []
            e = st["aim_x"] - b[0]
            self.stick = (max(-1.0, min(1.0, lat_sign * gain * e)), 0.0)
            return []
        while st["k"] < max_ticks and not done():
            if not on():
                engages += 1
                if not self.use(body1, on, n=200)["done"]:
                    break
                st["ball"], st["cores"] = None, {}
            k0 = st["k"]
            self.run(max_ticks - st["k"], on_tick=fn)
            if st["k"] == k0 or self.sb.read(self.pd, 0x50).split(b"\0")[0] != lvl:
                break
        self.stick = (0.0, 0.0)
        return {"won": done(), "ticks": st["k"], "crashes": st["crashes"], "most_lit": st["lit_max"],
                "engages": engages}


def _angle(d, w) -> float:
    n = math.sqrt(sum(c * c for c in w)) or 1.0
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(d[i] * w[i] for i in range(3)) / n))))

"""Reach: what a level's geometry and wiring let the player reach.

The reach model for one level (REORG_PLAN Phase R1, Steps R1.3a-c;
reach v6 of the randomizer evidence, ported as a model):

1. The wiring (:mod:`.wiring`) decides which driven solids, damage
   volumes and pushes are there at load, which toggled solids crumble
   under the player's own touch, and what switches each mechanism.
2. The collision's solid spans (:mod:`.geometry`), each profile's floors
   and regions (:mod:`.floors`), the air components, and the region
   edges: flights (:mod:`.flights`), swimming, climbing, slides and rides
   (:mod:`.moves`), updrafts by the calibration law, and the carries of
   the currents the swim stroke cannot beat (they follow the current's
   own water).
3. Teleports from every playerLocation's ``teleport`` plug, rides on
   platforms whose link curves give their stops, and the gates
   (:mod:`.gates`): every toggled solid, driven damage volume and door,
   with the requirement its wiring, its generated gate or its blocker
   family gives; the barrier crossings that bypass a shut gate need a
   skip.
4. The anchors (exits, spots, save points, locks, seals, keylords,
   barriers), the spawn, the events reach sets (pads, pickups, arrivals)
   and the zones: the strongly connected components under free movement.

``Reach(lv, env, db=database)`` runs it all for a level of the database
(the planner loader's :class:`~azurkit.tools.randomizer.planner.loader.Database`);
without ``db`` (a hand-built mesh) it stops after the gates, and with
``flights=False`` after the floors and regions.  Authoring only (numpy,
a runtime dependency): the planner and the writer never import it.
Coordinates stay in memory: nothing here prints or stores one.
Labels: [verified] a command or capture; [verified static] code or
config read; [inferred]; [proposal] a policy number.
"""

from __future__ import annotations

import collections
import math
import re
import struct

import numpy as np

from azurkit.tools.randomizer import levels as L
from azurkit.tools.randomizer.draft import envelope
from devkit.rando.draft.coverage import Coverage
from devkit.rando.draft.export import derive_inputs
from azurkit.tools.randomizer.draft.floors import DERIVED, PROFILES, Walk, lookup
from devkit.rando.draft.flights import Env, OverTest, _hits, jump_edges
from devkit.rando.draft.gates import ATTACK_REACH, CURRENT_SKIPS, PICK_STAND, Gates, free_edge, probe_class
from azurkit.tools.randomizer.draft.geometry import (
    CAT_DAMAGE, CAT_NAME, CAT_PUSH, CAT_RIG, CAT_TOGGLE, CAT_WATER, CELL, SOLID_CATS, Air, Obstacles, RadiusIndex, Spans,
    Volumes, raster)
from devkit.rando.draft.moves import (
    LETHAL_FALL_M, RIG_DECK_M2, RIG_RING, Slopes, WaterGrid, climb_edges, rig_edges, slide_edges, swim_edges,
    water_fall_edges)
from azurkit.tools.randomizer.draft.wiring import (
    F_TRUE, Wiring, and_req, blockers, f_and, families, req_dnf, saved_names)
from azurkit.tools.randomizer.art import collision, nodes

SPRING_BLOCK_S = 0.5   # [proposal] an autoSpring pad of springboard <= 0.5 hops the body S m: no jump takes off from it
ITEM_SHORT_M = 0.3     # [inferred] the segment from a floor sample to an item stops this short of it (they touch)
G_, DT_ = 9.8, 1.0 / 30.0           # [verified static] physics.GRAVITY, the 1/30 s tick
SWIM_MPS = envelope.SWIM["target_mps"]   # 10.0 [verified xemu s6]: the swim stroke
RIDE_RING_M, RIDE_DZ_M = 8.0, 1.5   # a spawn riding a lift lands within 8 m of its deck at the stop, floor within 1.5 m
ROLL_ANCHOR_M = 110.0   # [proposal, default taken under D115] a rollthrough starts from the floor within this of its anchors
ROLL_MAX_M = 45.0       # [verified xemu skips-h S1: 9-11 rolls at 6.0-6.2 m/s, 5.6-6.7 s] a roll chain's straight reach
# Each level's spawn (defaults taken under D115: the arrival the vanilla route first uses; w3 starts from all four w1
# arrivals, each reached in w1 with no item)
SPAWN = {"w1": ["startspot"], "town": ["W1_TownShape"], "e2": ["Town_E2"], "f1": ["Town_F1"], "a1": ["E6_A1"],
         "w3": ["W1_W3a", "W1_W3b", "W1_W3c", "W1_W3d"], "w2": ["W1_W2"], "e7": ["E2_E7"], "w4": ["W1_W4"],
         "f3": ["W4_F3"], "e5": ["E2_E5"], "f2": ["E5_F2"], "f4": ["F2_F4b"], "e6": ["E2_E6"], "f6": ["F1_F6"],
         "airship": ["startspotShape"], "a3": ["startspotShape"], "a5": ["startspot"], "a6": ["A1_A6Shape"],
         "life": ["startspot"], "d1": ["startspotShape"], "d2": ["D1_D2"]}


class Reach(Gates, Coverage):
    """The reach model of one level (the module docstring).  ``W[prof]`` is
    each profile's :class:`~.floors.Walk`, ``E[prof]`` maps (from node, to
    node) to its edges (land regions, then ``wg.n`` swim regions from
    ``W[prof].nreg`` on)."""

    def __init__(self, lv, env: Env | None = None, *, db=None, flights: bool = True):
        self.lv, self.name = lv, lv.name
        self.env = env if env is not None or not flights else Env.kept()
        self.gen = db.generated.get(lv.name, {}) if db is not None else {}
        # the rest of the database only as export.derive_inputs projects it, which the stamp hashes (Step R1.32)
        ins = derive_inputs(lv.name, db.tricks, db.levels.get(lv.name, {}), db.generated) if db is not None \
            else derive_inputs(lv.name, {}, {}, {})
        self.toml, self.exits_into = ins["level"], ins["exits_into"]
        self.tricks = {s["id"]: s for s in ins["skip"]}
        self.wire = Wiring(lv, self.gen, self.toml)
        # A driven gameSolid, damage or pushEnable is there at load when its first frame's propagated value is non-zero
        # (every node starts fully dirty [verified static for the combiner factory, inferred for the rest]); where the
        # drivers are not decoded, the stored value stays
        self.init_changed = []
        for o in lv.owners:
            plug = {CAT_TOGGLE: "gameSolid", CAT_DAMAGE: "damage", CAT_PUSH: "pushEnable"}.get(o["cat"])
            if o["kind"] != "platform" or plug is None or plug not in o["driven"]:
                continue
            sg = self.wire.plug(o["oi"], plug)
            o["present_stored"] = o["present"]
            if sg.init is not None and (sg.init != 0.0) != o["present"]:
                o["present"] = sg.init != 0.0
                self.init_changed.append(o["oi"])
        self.present = np.array([o["present"] for o in lv.owners], dtype=bool)
        # a toggled solid that only its own touch removes (a1's crack blocks: solid until about 3.8 s after the first
        # touch) is a floor the logic walk stands on
        self.crumble = set()
        for o in lv.owners:
            if o["kind"] == "platform" and o["cat"] == CAT_TOGGLE and o["present"] and "gameSolid" in o["driven"]:
                t_ = self.wire.terms(self.wire.plug(o["oi"], "gameSolid").off)
                if t_ == [(frozenset([f"touch:{o['G']}:{o['R']}"]), frozenset())]:
                    self.crumble.add(o["oi"])
        self.pairs = raster(lv, np.nonzero(np.isin(lv.tri_cat, SOLID_CATS))[0])
        self.pmask = self.present[lv.tri_owner[self.pairs[3]]]
        self.spans = Spans(lv, *(x[self.pmask] for x in self.pairs))
        self.water_oids = [o["oi"] for o in lv.owners if o["cat"] == CAT_WATER]
        self.damage_oids = [o["oi"] for o in lv.owners if o["cat"] == CAT_DAMAGE]
        # drag currents [inferred]: a push volume switched by the same driver as a link-driven damage volume (w1's
        # whirlpool PushFields and its kill field) pulls the swimmer into that field: it counts as part of it
        dmg_drv = {tuple(lv.driver_of(oi, ("damage",))) for oi in self.damage_oids
                   if "damage" in lv.owners[oi]["driven"]} - {()}
        self.drag_oids = [o["oi"] for o in lv.owners if o["cat"] == CAT_PUSH and "pushEnable" in o["driven"]
                          and tuple(lv.driver_of(o["oi"], ("pushEnable",))) in dmg_drv]
        self.damage_oids += self.drag_oids
        self.push_classify()
        self.water_vol = Volumes(lv, self.water_oids)
        self.damage_vol = Volumes(lv, self.damage_oids)
        self.dmg_present = {oi for oi in self.damage_oids if lv.owners[oi]["present"]}
        self.swim_block_vol = Volumes(lv, [c["oi"] for c in self.currents if c["blocks_swim"]])
        self.flight_vol = Volumes(lv, sorted(set(self.damage_oids) | {d["oi"] for d in self.downdrafts}))
        self.wg = WaterGrid(lv, self.water_vol, self.damage_vol, self.dmg_present, self.spans, self.swim_block_vol)
        self.air = Air(lv, self.spans)
        self.slopes = Slopes(lv)     # the slides' faces (AZ-359): slid down, never walked
        self.W, self.E, self.rig_info, self.flight_stats, self.carriers = {}, {}, {}, {}, {}
        self._padc, self._bbc = {}, {}
        down = {d["oi"] for d in self.downdrafts}
        self.over_groups = self._over_groups()
        self.over_test = OverTest(lv, self.over_groups, PROFILES["logic"]["height"])
        for prof in DERIVED:
            self._profile(prof, flights, down)
        if not flights:
            return
        self.base = {prof: self.W[prof].nreg for prof in DERIVED}
        self.flagdef = {}
        self.teleport_edges()
        self.ride_edges()
        # a rig whose decoded ride joins regions stands for its own guessed ride (moves.rig_edges); one whose decoded
        # stops find no regions (town's grate elevator) keeps the guess (AZ-353)
        done = {r["name"] for r in self.rides if r.get("decoded") and r.get("edges")}
        for prof in DERIVED:
            for k, es in self.E[prof].items():
                es[:] = [e for e in es if not (e["kind"] == "rig" and e["conf"] == "probe-needed" and e.get("via") in done)]
            self.rig_info[prof] = [r for r in self.rig_info[prof] if r["name"] not in done]
        self.blockers = blockers(lv, self.gen)
        self.families = families()
        self.gates = self.gate_groups()
        self.doors = self.find_doors()       # wired doors join self.gates; undecoded action doors stay in self.doors
        self.wire_gates()
        self.undecoded = {g["id"] for g in self.gates if g["requires"] is None}
        self.gate_by_id = {g["id"]: g for g in self.gates}
        self.rig_gating()
        for g in self.gates + self.doors:
            self.gate_variant(g)
        self.resolve_overflights()
        self.resolve_hazard_flights()
        if db is None:
            return
        self.anchors()
        self.spawn_nodes()
        self.flag_nodes()
        self.zones()
        self.barrier_cut()
        z0 = self.zone_of.copy()
        self.zones()
        if not (self.zone_of == z0).all():
            raise AssertionError(f"{self.name}: a barrier crossing edge lay inside a zone")
        self._adjc, self._bfs_flags = {}, None
        self.locations()
        self.coverage()

    def _profile(self, prof, flights, down):
        """One profile's floors, regions and region edges."""
        lv, p = self.lv, PROFILES[prof]
        obst = Obstacles(lv, self.pairs, self.pmask, p["floor_nz"])
        w = Walk(lv, self.spans, prof, self.water_vol, self.dmg_present, self.damage_vol, obst,
                 self.crumble if prof == "logic" else None)
        if prof == "logic":
            w.acomp = self.air.comp_of(w.sidx)
        self.W[prof] = w
        if not flights:
            return
        # E: (from, to) -> [edge, ...]; several edges may join one pair, and readers take the cheapest usable one
        E = self.E[prof] = collections.defaultdict(list)
        stats = self.flight_stats[prof] = {}
        blockers_ = np.isin(w.top_owner, list(self.spring_blockers)) if prof == "logic" else None
        for k, e in jump_edges(lv, self.spans, w, self.env, p["tiers"], sweep=(prof == "logic"),
                               haz=(self.flight_vol, self.dmg_present | down), stats=stats, down=down,
                               blockers=blockers_, over=self.over_test if prof == "logic" else None).items():
            if prof == "phys":
                e["ranks"] = e["ranks"] * 4      # one tier, repeated so every reader sees 4
            E[k[:2]].append(e)
        for a_, b_ in w.cross:
            for x_, y_ in ((a_, b_), (b_, a_)):
                E[(x_, y_)].append({"kind": "walk", "conf": "modelled", "ranks": [0, 0, 0, 0], "dh": 0.0, "slip": True,
                                    "why": "onto or off a near-flat slippery floor (0x8051 / slippery bit; walking it "
                                           "unmeasured)"})
        if prof == "logic" and any(c["blocks_swim"] for c in self.currents) and self.wg.n:
            # where the land enters a blocking current's water, then that water split by who reaches it, then the swim
            # edges on the split labels
            swim_edges(lv, w, self.wg, w.nreg, self.spans, self.air, None)
            self.split_blocked_water(w)
            w.blk_entry = collections.defaultdict(set)
        for k, e in swim_edges(lv, w, self.wg, w.nreg, self.spans if prof == "logic" else None,
                               self.air if prof == "logic" else None, stats).items():
            E[k].append(e)
        for k, e in water_fall_edges(lv, w, self.wg, w.nreg, self.spans).items():
            E[k].append(e)
        for k, e in climb_edges(lv, w)[0].items():
            E[k].append(e)
        for k, es in self.updraft_edges(prof, w).items():
            E[k].extend(es)
        for k, es in self.current_edges(prof, w).items():
            E[k].extend(es)
        for k, e in slide_edges(lv, w, self.slopes, self.wg, self.air if prof == "logic" else None).items():
            E[k].append(e)
        re_, self.rig_info[prof] = rig_edges(lv, w)
        for k, e in re_.items():
            E[k].append(e)

    # ---- push volumes (calib §3: inside an air push volume the push's axis component tends to push / 0.9 with
    # c = 0.035404 per tick, and gravity is off while pushZ > 0)
    def push_classify(self):
        """Every non-drag push volume that can be on (there at load, or
        switched by a decoded or undecoded driver): updrafts (pushZ > 0.5),
        downdrafts (pushZ < -0.5) and horizontal pushes (|pushX, pushY| >
        0.5); and the solid autoSpring pads of springboard <= 0.5 (jump
        blockers)."""
        lv = self.lv
        self.updrafts, self.downdrafts, self.currents = [], [], []
        self.spring_blockers = set()
        for o in lv.owners:
            if o["kind"] != "platform":
                continue
            a = o["attrs"]
            if (o["word"] & collision.W_SOLID) and (o["word"] & collision.W_AUTOSPRING) \
                    and a.get("springboard", 0.0) <= SPRING_BLOCK_S:
                self.spring_blockers.add(o["oi"])
            if o["cat"] != CAT_PUSH or o["oi"] in self.drag_oids:
                continue
            px, py, pz = (float(a.get(k, 0.0)) for k in ("pushX", "pushY", "pushZ"))
            if o["present"]:
                alts = [(frozenset(), frozenset())]
            elif "pushEnable" in o["driven"]:
                alts = self.wire.terms(self.wire.plug(o["oi"], "pushEnable").on)
            else:
                alts = []
            if not (alts is None or bool(alts)):
                continue
            ent = {"oi": o["oi"], "name": o["name"], "push": (px, py, pz), "alts": alts, "present": bool(o["present"]),
                   "switched": "pushEnable" in o["driven"], "moved": bool(o["moved"] or o["approx"])}
            if pz > 0.5:
                self.updrafts.append(ent)
            elif pz < -0.5:
                self.downdrafts.append(ent)
            hs = math.hypot(px, py)
            if hs > 0.5:
                m = o["world"]
                p0 = np.array(nodes.apply(m, (0.0, 0.0, 0.0)))
                rp = np.array(nodes.apply(m, (px, py, 0.0))) - p0
                rp = rp[:2] / max(float(np.hypot(rp[0], rp[1])), 1e-9)
                speed = hs / envelope.PUSH_TERM_DIV
                # the push acts along the volume's own axes, turned by its rotation, and it moves only a swimming body
                # [verified xemu skips-h S1]: a push of at least the 10 m/s stroke is a barrier to swimmers only
                self.currents.append(dict(ent, dir=(float(rp[0]), float(rp[1])), speed=round(speed, 2), ambiguous=False,
                                          blocks_swim=speed >= SWIM_MPS and not ent["moved"], blocks_walk=False))

    def _vol_cols(self, oi):
        """(columns, per-column lo, hi, XY centre) of a volume owner's mesh (in memory)."""
        col, zlo, zhi, _ = raster(self.lv, self.lv.tris_of(oi))[:4]
        if not len(col):
            return None
        u, inv = np.unique(col, return_inverse=True)
        lo = np.full(len(u), np.inf)
        hi = np.full(len(u), -np.inf)
        np.minimum.at(lo, inv, zlo)
        np.maximum.at(hi, inv, zhi)
        P = self.lv.P[self.lv.tris_of(oi)].reshape(-1, 3)
        return u, lo, hi, (float(P[:, 0].mean()), float(P[:, 1].mean()))

    def _ring(self, cols, r):
        rr = range(-r, r + 1)
        return np.unique(np.concatenate([np.asarray(cols) + dx + dy * self.lv.NX for dx in rr for dy in rr]))

    @staticmethod
    def _samples(w, cols):
        a, c = lookup(w.u, w.a, w.c, np.asarray(cols, dtype=np.int64))
        out = [(a + k)[k < c] for k in range(w.mx)]
        return np.concatenate(out) if out else np.zeros(0, dtype=np.int64)

    def _alt_edges(self, edges, a_, b_, base, alts, verb="switched on by"):
        """One edge per alternative of a decoded condition (flags = its pads,
        needs = its items); alts None: probe-needed."""
        if alts is None:
            edges.setdefault((a_, b_), dict(base, conf="probe-needed",
                                            why=base["why"] + "; switched by a driver that is not decoded"))
            return
        for pads, items in alts:
            e = dict(base)
            if pads or items:
                e["why"] = base["why"] + f"; {verb} {self.alts_req([(pads, items)])}"
            if pads:
                e["flags"] = sorted(pads)
            if items:
                e["needs"] = sorted(items)
            key = (a_, b_) if not (pads or items) else (a_, b_, tuple(sorted(pads)), tuple(sorted(items)))
            edges.setdefault(key, e)

    def updraft_edges(self, prof, w):
        """Updrafts by the calib law [verified xemu, placed]: from the walk
        regions whose body is inside the volume (or at its foot) the body
        rises at vz' = vz + 0.035404 (pushZ / 0.9 - vz) per tick with no
        gravity to the volume's top, then flies ballistic (apex = top + v^2 /
        2g), capped 2 m under the first solid above the entry; it lands on
        any walk region within 1.5 m of the column's footprint up to that
        apex, in the column's air component, unless the fall from the apex is
        lethal [proposal: the landing ring].  A switched volume's edges carry
        its switch's decoded condition; an undecoded switch leaves them
        probe-needed (class push)."""
        lv, edges = self.lv, {}
        for u in self.updrafts:
            if lv.owners[u["oi"]]["attrs"].get("water", 0.0):
                continue
            vc = self._vol_cols(u["oi"])
            if vc is None:
                continue
            cols, lo, hi, _ = vc
            zt, zb = float(hi.max()), float(lo.min())
            pos = {int(c): k for k, c in enumerate(cols.tolist())}
            js = self._samples(w, self._ring(cols, 1))
            js = js[w.reg_soft[js] >= 0] if len(js) else js
            if not len(js):
                continue
            kk = np.array([pos.get(int(c), -1) for c in w.col[js].tolist()])
            inside = (kk >= 0) & (w.z[js] >= np.where(kk >= 0, lo[np.maximum(kk, 0)], 0) - 2.0) & \
                (w.z[js] <= np.where(kk >= 0, hi[np.maximum(kk, 0)], 0))
            foot = np.abs(w.z[js] - zb) <= 2.0
            ent_j = js[inside] if inside.any() else js[foot]
            if not len(ent_j):
                continue
            zin = max(float(w.z[ent_j].min()), zb)
            V = u["push"][2] / envelope.PUSH_TERM_DIV
            z, vz, t = zin, 0.0, 0
            while z < zt and t < 6000:
                vz += envelope.PUSH_C * (V - vz)
                z += vz * DT_
                t += 1
            apex = zt + vz * vz / (2 * G_)
            a, c = self.spans.range_of(cols)
            caps = []
            for q in range(len(cols)):
                b = [float(self.spans.bot[int(a[q]) + k]) for k in range(int(c[q])) if self.spans.bot[int(a[q]) + k] > zin + 0.5]
                caps.append(min(b) if b else np.inf)
            top = min(apex, float(np.median(caps)) - 2.0)
            if top <= zin + 0.5:
                continue
            comp = None
            if prof == "logic":
                g_ = self.air.comp_of(self.air.gap_at(cols, np.full(len(cols), min(zin + 1.0, top))))
                comp = set(g_[g_ >= 0].tolist())
            land = self._samples(w, self._ring(cols, 3))
            land = land[(w.reg[land] >= 0) & (w.z[land] <= top - 0.1) & (w.z[land] > top - LETHAL_FALL_M)]
            if comp is not None:
                land = land[np.isin(w.acomp[land], list(comp))]
            src = sorted(set(w.reg_soft[ent_j].tolist()) - {-1})
            dst = sorted(set(w.reg[land].tolist()))
            alts = u["alts"] if u["switched"] else [(frozenset(), frozenset())]
            # the column the body rises through: a pad in it is touched from the updraft's entry (pad_nodes)
            self.carriers.setdefault(prof, []).append((set(cols.tolist()), zin, top + PICK_STAND, set(src), alts))
            hz = {}
            for j_ in land.tolist():
                r_ = int(w.reg[j_])
                hz[r_] = max(hz.get(r_, -np.inf), float(w.z[j_]))
            base = {"kind": "push", "conf": "modelled", "ranks": [0, 0, 0, 0], "via": u["name"],
                    "why": f"updraft {u['name']} (pushZ {u['push'][2]:g}): rises at up to {V:.1f} m/s with no gravity, "
                           f"about {top - zt:+.1f} m over its top (calib law, verified xemu)"}
            for a_ in src:
                for b_ in dst:
                    if a_ != b_:
                        self._alt_edges(edges, a_, b_, dict(base, dh=hz[b_] - zin), alts)
        return self._flat(edges)

    @staticmethod
    def _flat(edges):
        """(a, b[, alt]) -> edge  =>  (a, b) -> [edge]."""
        out = collections.defaultdict(list)
        for k, e in edges.items():
            out[k[:2]].append(e)
        return out

    CARRY_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))

    def _water_band(self, cols, lo, hi):
        """Does column cols[i] hold a live water node overlapping [lo[i], hi[i]] by WATER_PASS_M?"""
        wg = self.wg
        a, c = wg.range_of(np.asarray(cols, dtype=np.int64))
        res = np.zeros(len(cols), dtype=bool)
        for k in range(wg.maxper):
            v = k < c
            j = np.where(v, a + k, 0)
            res |= v & (wg.lab[j] >= 0) & (np.minimum(hi, wg.hi[j]) - np.maximum(lo, wg.lo[j]) >= WaterGrid.WATER_PASS_M)
        return res

    def carry_graph(self):
        """Where a swimmer inside a blocking current's water is carried,
        along that water only.  The nodes are the water nodes inside the
        blocking currents.  A swimmer moves with velocity P d + S u (P the
        push's terminal speed along its rotated axis d, S the 10 m/s stroke,
        |u| <= 1), so only within asin(S/P) of d: a step to an 8-neighbour
        node whose interval overlaps by WATER_PASS_M (a diagonal one only
        when both orthogonal columns hold such water) is taken when its
        direction lies in that cone.  Into another blocking current's water
        it goes on under that one's cone; into free water it is an exit.
        The steps form a DAG (strong components are folded anyway), so each
        node's exits are the union over its successors', sinks first
        [computed]."""
        if getattr(self, "_carry", None) is not None:
            return self._carry
        lv, wg = self.lv, self.wg
        NX = lv.NX
        P_ = WaterGrid.WATER_PASS_M
        cur = {c["oi"]: c for c in self.currents if c["blocks_swim"]}
        bi = np.nonzero((wg.blk_own >= 0) & (wg.lab >= 0))[0]
        pos = np.full(len(wg.col), -1, dtype=np.int64)
        pos[bi] = np.arange(len(bi))
        own = wg.blk_own[bi]
        oids = np.array(sorted(cur), dtype=np.int64)
        if not len(bi) or not len(oids):
            self._carry = {"bi": bi, "pos": pos, "own": own, "comp": np.zeros(0, dtype=np.int64), "ex": [], "pred": {},
                           "order": [], "entries": tuple(np.zeros(0, dtype=np.int64) for _ in range(4)), "steps": 0,
                           "exits": 0, "components": 0}
            return self._carry
        k_ = np.searchsorted(oids, own)
        dxs = np.array([cur[o]["dir"][0] for o in oids.tolist()])[k_]
        dys = np.array([cur[o]["dir"][1] for o in oids.tolist()])[k_]
        cmin = np.array([math.cos(math.asin(min(1.0, SWIM_MPS / max(cur[o]["speed"], 1e-9)))) for o in oids.tolist()])[k_]
        ci, lo_i, hi_i = wg.col[bi], wg.lo[bi], wg.hi[bi]
        ix = ci % NX
        e_s, e_d, x_p, x_l, n_p, n_l, n_n, n_dot = [], [], [], [], [], [], [], []
        for sx, sy in self.CARRY_STEPS:
            valid = (ix + sx >= 0) & (ix + sx < NX)
            nc = np.where(valid, ci + sx + sy * NX, -1)
            a, c = wg.range_of(nc)
            c = np.where(valid, c, 0)
            ln = math.hypot(sx, sy)
            cosang = dxs * (sx / ln) + dys * (sy / ln)
            allowed = cosang >= cmin - 1e-9
            for k in range(wg.maxper):
                v = k < c
                j = np.where(v, a + k, 0)
                lo_, hi_ = np.maximum(lo_i, wg.lo[j]), np.minimum(hi_i, wg.hi[j])
                ok = v & (wg.lab[j] >= 0) & (hi_ - lo_ >= P_)
                if sx and sy and ok.any():
                    q0 = np.nonzero(ok)[0]
                    diag = self._water_band(ci[q0] + sx, lo_[q0], hi_[q0]) & \
                        self._water_band(ci[q0] + sy * NX, lo_[q0], hi_[q0])
                    ok[q0[~diag]] = False
                q = np.nonzero(ok)[0]
                if not len(q):
                    continue
                jq = j[q]
                inner = wg.blk_own[jq] >= 0
                m1 = inner & allowed[q]
                e_s.append(q[m1])
                e_d.append(pos[jq[m1]])
                m2 = ~inner & allowed[q]
                x_p.append(q[m2])
                x_l.append(wg.lab[jq[m2]])
                m3 = ~inner
                n_p.append(q[m3])
                n_l.append(wg.lab[jq[m3]])
                n_n.append(jq[m3])
                n_dot.append(-cosang[q[m3]])

        def cat(xs, dt=np.int64):
            return np.concatenate(xs).astype(dt) if xs else np.zeros(0, dtype=dt)
        src, dst = cat(e_s), cat(e_d)
        ncomp, comp = _strong_components(len(bi), src, dst)
        cs, cd = comp[src], comp[dst]
        m = cs != cd
        succ = collections.defaultdict(set)
        for a_, b_ in zip(cs[m].tolist(), cd[m].tolist()):
            succ[a_].add(b_)
        own_ex = collections.defaultdict(set)
        xp, xl = cat(x_p), cat(x_l)
        for p_, l_ in zip(comp[xp].tolist(), xl.tolist()):
            own_ex[p_].add(l_)
        pred = collections.defaultdict(list)
        outdeg = np.zeros(ncomp, dtype=np.int64)
        for a_, bs in succ.items():
            outdeg[a_] = len(bs)
            for b_ in bs:
                pred[b_].append(a_)
        ex = [None] * ncomp
        intern = {}
        order = []
        st = np.nonzero(outdeg == 0)[0].tolist()
        while st:
            c_ = st.pop()
            order.append(c_)
            s_ = set(own_ex.get(c_, ()))
            for b_ in succ.get(c_, ()):
                s_ |= ex[b_]
            fs = frozenset(s_)
            ex[c_] = intern.setdefault(fs, fs)
            for p_ in pred.get(c_, ()):
                outdeg[p_] -= 1
                if outdeg[p_] == 0:
                    st.append(p_)
        if any(x is None for x in ex):
            raise AssertionError("carry graph: a cycle survived the strong components")
        self._carry = {"bi": bi, "pos": pos, "own": own, "comp": comp, "ex": ex, "pred": pred, "order": order,
                       "entries": (cat(n_p), cat(n_l), cat(n_n), np.concatenate(n_dot) if n_dot else np.zeros(0)),
                       "steps": int(len(src)), "exits": int(len(xp)), "components": int(ncomp)}
        return self._carry

    def split_blocked_water(self, w):
        """A blocking current's water is no place a swimmer reaches as a whole:
        each of its nodes is reached from the entries whose carry passes it
        (the swim regions next to it and the logic land regions that enter
        it), to a fixpoint along the carry DAG; its swim labels are split by
        that source set, so a pickup, pad or exit inside the current is
        reached exactly when one of its sources is [computed]."""
        wg = self.wg
        Cg = self.carry_graph()
        bi, pos, comp, pred, order = Cg["bi"], Cg["pos"], Cg["comp"], Cg["pred"], Cg["order"]
        if not len(bi):
            return
        seeds = collections.defaultdict(set)
        e_pos, e_lab = Cg["entries"][:2]
        for p_, O in zip(e_pos.tolist(), e_lab.tolist()):
            seeds[int(comp[p_])].add(("w", int(O)))
        for r_, nds in getattr(w, "blk_entry", {}).items():
            for n_ in nds:
                if pos[n_] >= 0:
                    seeds[int(comp[pos[n_]])].add(("l", int(r_)))
        S = [None] * len(order)
        intern = {}
        for c_ in reversed(order):              # every predecessor before its successors
            s_ = set(seeds.get(c_, ()))
            for p_ in pred.get(c_, ()):
                s_ |= S[p_]
            fs = frozenset(s_)
            S[c_] = intern.setdefault(fs, fs)
        lab0 = wg.lab.copy()
        first = {}
        for q, n_ in enumerate(bi.tolist()):
            first.setdefault((int(lab0[n_]), S[comp[q]]), n_)
        per = collections.defaultdict(list)
        for k_, n_ in first.items():
            per[k_[0]].append((n_, k_))
        key = {}
        nxt = wg.n
        for L_ in sorted(per):
            cls = sorted(per[L_])
            keep = next((k_ for _, k_ in cls if not k_[1]), cls[0][1])
            key[keep] = L_
            for _, k_ in cls:
                if k_ not in key:
                    key[k_] = nxt
                    nxt += 1
        newlab = lab0.copy()
        for q, n_ in enumerate(bi.tolist()):
            newlab[n_] = key[(int(lab0[n_]), S[comp[q]])]
        wg.lab0 = lab0
        wg.lab = newlab
        good = newlab >= 0
        kk = np.unique(newlab[good].astype(np.int64) * (int(wg.col.max()) + 1) + wg.col[good])
        wg.count = np.bincount(kk // (int(wg.col.max()) + 1), minlength=nxt)
        wg.n = nxt
        wg.lab_blocked = set(newlab[wg.blk & good].tolist())
        self.class_src = {lab_: src_ for (_, src_), lab_ in key.items()}
        self.class_own = {}
        for q, n_ in enumerate(bi.tolist()):
            self.class_own.setdefault(int(newlab[n_]), int(wg.blk_own[n_]))
        self.blocked_split = {"labels_before": len(per), "labels_after": len(key),
                              "sources": len({x for k_ in key for x in k_[1]})}

    def current_edges(self, prof, w):
        """The currents the stroke cannot beat (terminal speed at least 10 m/s
        [verified xemu s6]): a swim region next to one (or, in the logic
        profile, a land region that enters it) joins the exits of the node
        it enters (``push``, modelled), and each such carry between two swim
        regions is a ``current`` edge the other way, probe-needed, that
        needs a held skip.  Swimming into the current's water is a ``swim``
        edge (a sink: the push edges carry the swimmer on).  A tricks.toml
        skip that names a crossing (CURRENT_SKIPS) joins the floor in and
        beside the band near its anchor spots to the largest water the
        band's upstream face opens on within a roll chain's reach."""
        edges = {}
        wg = self.wg
        nb = w.nreg
        if not wg.n or not any(c["blocks_swim"] for c in self.currents):
            return self._flat(edges)
        Cg = self.carry_graph()
        e_pos, e_lab, e_node, e_dot = Cg["entries"]
        own, comp, ex, pos = Cg["own"], Cg["comp"], Cg["ex"], Cg["pos"]
        land = getattr(w, "blk_entry", {})
        names = {c["oi"]: c["name"] for c in self.currents}
        for C, src_ in sorted(getattr(self, "class_src", {}).items()):
            vn = names.get(self.class_own.get(C), "a current")
            for kind_, x_ in sorted(src_):
                if kind_ == "l" and prof != "logic":
                    continue
                a_ = nb + x_ if kind_ == "w" else x_
                edges.setdefault((a_, nb + C, "enter"), {
                    "kind": "swim", "conf": "geometry", "ranks": [0, 0, 0, 0], "via": vn,
                    "why": f"into {vn}'s water where its push carries a swimmer who enters from here (split_blocked_water)"})
        for c in self.currents:
            if not c["blocks_swim"]:
                continue
            oi = c["oi"]
            alts = c["alts"] if c["switched"] else [(frozenset(), frozenset())]
            carry = {"kind": "push", "conf": "modelled", "ranks": [0, 0, 0, 0], "via": c["name"],
                     "why": f"a swimmer carried by {c['name']} (push {math.hypot(*c['push'][:2]):g}: {c['speed']:.1f} m/s "
                            f"terminal) along its own water (carry_graph)"}
            m = own[e_pos] == oi if len(e_pos) else np.zeros(0, dtype=bool)
            water = set()
            for p_, O in zip(e_pos[m].tolist(), e_lab[m].tolist()):
                for X in ex[comp[p_]]:
                    if X != O:
                        water.add((nb + O, nb + X))
            fromland = set()
            for r_, nds in land.items():
                for n_ in nds:
                    p_ = pos[n_]
                    if p_ < 0 or own[p_] != oi:
                        continue
                    for X in ex[comp[p_]]:
                        fromland.add((r_, nb + X))
            for a_, b_ in sorted(water | fromland):
                if a_ != b_:
                    self._alt_edges(edges, a_, b_, carry, alts)
            against = {"kind": "current", "conf": "probe-needed", "ranks": [0, 0, 0, 0], "via": c["name"],
                       "current": {"volume": c["name"], "skip": None, "speed": c["speed"]},
                       "why": f"a swimmer against {c['name']}'s push ({c['speed']:.1f} m/s terminal, at least the 10 m/s "
                              f"stroke) along the water a carry follows: blocked unless a skip (a generated held skip)"}
            for a_, b_ in sorted(water):
                if a_ != b_:
                    edges.setdefault((b_, a_, "against"), against)
            hand = next((h for h in CURRENT_SKIPS.get(self.name, ()) if c["name"] in h["volumes"]), None)
            if hand:
                self._hand_current_edges(edges, w, c, hand, e_lab[m], e_node[m], e_dot[m])
        return self._flat(edges)

    def _hand_current_edges(self, edges, w, c, hand, e_lab, e_node, e_dot):
        """The hand skip's crossing: from the floor in or beside the band
        (within ROLL_ANCHOR_M of the skip's anchor spots), against the push,
        to the largest swim region the band's upstream face opens on whose
        entry node is within ROLL_MAX_M of such a floor sample.  The roll
        follows the shore's floor, so no straight-path test is used."""
        lv, wg, nb = self.lv, self.wg, w.nreg
        vc = self._vol_cols(c["oi"])
        if vc is None:
            return
        cols, lo, hi, _ = vc
        zl, zh = float(lo.min()), float(hi.max())
        js = self._samples(w, self._ring(cols, 1))
        js = js[(w.reg[js] >= 0) & (w.z[js] >= zl - 1.0) & (w.z[js] <= zh + 1.0)] if len(js) else js
        names = {s_["name"]: s_["id"] for s_ in self.gen.get("spots", [])}
        anchors = [lv.rec_points(names[a_])[0][0] for a_ in hand.get("anchors", ()) if a_ in names]
        if anchors and len(js):
            near = np.zeros(len(js), dtype=bool)
            for ap in anchors:
                near |= np.hypot(w.x[js] - ap[0], w.y[js] - ap[1]) <= ROLL_ANCHOR_M
            js = js[near]
        up = e_dot > 0.3
        tgt_node, tgt_lab = e_node[up], e_lab[up]
        if not len(js) or not len(tgt_node):
            return
        tx, ty = lv.cxy(wg.col[tgt_node])
        best = {}
        for q, t_ in zip(*_ball_pairs(np.c_[w.x[js], w.y[js]], np.c_[tx, ty], ROLL_MAX_M)):
            k_ = (int(w.reg[js[q]]), int(tgt_lab[t_]))
            dd = math.hypot(tx[t_] - w.x[js[q]], ty[t_] - w.y[js[q]])
            if dd < best.get(k_, (np.inf,))[0]:
                best[k_] = (dd, int(js[q]), int(t_))
        reg_ = self.tricks.get(hand["skip"], {})
        ok = reg_.get("status") == "in_logic" and reg_.get("confirmed") not in (None, "no")
        hreq = req_dnf(reg_.get("requires", "true"))
        hneeds = sorted(x[2:] for x in next(iter(hreq))) if hreq and len(hreq) == 1 else []
        base = {"kind": "current", "ranks": [0, 0, 0, 0], "via": c["name"], **({"needs": hneeds} if hneeds else {}),
                "current": {"volume": c["name"], "skip": hand["skip"], "speed": c["speed"]},
                "why": f"a roll chain on the floor across {c['name']}'s band against its push ({hand['skip']}, "
                       f"{'confirmed' if ok else 'held'}), from near {' / '.join(hand.get('anchors', ())) or 'the band'}"}
        base.update({"conf": "skip", "skip_atom": True} if ok else {"conf": "probe-needed"})
        # the open water past the band: of the swim regions in reach, the largest [default taken under D115]
        if best:
            top_ = max({O for _, O in best}, key=lambda O: (int(wg.count[O]), -O))
            for (r_, O) in sorted(best):
                if O == top_ and r_ != nb + O:
                    edges.setdefault((r_, nb + O, "hand"), dict(base))

    # ---- flags: touch pads, hits, pickups and arrivals as events reach sets
    PAD_KINDS = ("touch", "action", "whack", "joystick", "hit")

    def flag_label(self, atom):
        kind, _, rest = atom.partition(":")
        if kind == "loc":
            return f"{self.name}.loc.r{rest.rsplit('/r', 1)[1]}.collected"
        G, R = (int(x) for x in rest.split(":"))
        nm = self.lv.graphs[G].names[R] or f"r{R}"
        stem = re.sub(r"[^A-Za-z0-9_]", "_", nm)
        dup = sum(1 for g_ in self.lv.graphs for n_ in g_.names if n_ == nm) > 1
        return f"{self.name}.{stem}{f'_g{G}r{R}' if dup else ''}.{'arrived' if kind == 'arrive' else kind}"

    def flag_event(self, atom):
        return f"event:{self.flag_label(atom)}"

    def flagdef_label(self, atom):
        kind, _, rest = atom.partition(":")
        if kind == "loc":
            return rest
        G, R = (int(x) for x in rest.split(":"))
        return f"{self.lv.graphs[G].names[R]} ({kind})"

    def alts_req(self, alts):
        """[(pads, items)] -> a §5.1 string (pads as event: atoms); [] -> false; None -> None."""
        if alts is None:
            return None
        parts = [and_req(*([self.flag_event(p) for p in sorted(pads)] + sorted(items))) for pads, items in alts]
        if not parts:
            return "false"
        if "true" in parts:
            return "true"
        return " | ".join(f"({p_})" if "&" in p_ and len(parts) > 1 else p_ for p_ in parts)

    def pad_nodes(self, atom, prof):
        """The nodes whose body touches a pad (a hit: within ATTACK_REACH of
        the shape; a pad an unconditional updraft carries the body through
        is touched from the updraft's entry)."""
        if (atom, prof) in self._padc:
            return self._padc[(atom, prof)]
        kind, _, rest = atom.partition(":")
        out = frozenset()
        oi = None if kind in ("loc", "arrive") else self.lv.by_rec.get(tuple(int(x) for x in rest.split(":")))
        if oi is not None:
            col, zl, zh, _ = raster(self.lv, self.lv.tris_of(oi))[:4]
            if kind != "hit":
                nds = set(self.footprint(oi, prof))
                if len(col):
                    cs = set(col.tolist())
                    for ccols, z0, z1, src, alts in self.carriers.get(prof, ()):
                        if alts and not any(p_ or i_ for p_, i_ in alts) and cs & ccols and float(zl.min()) <= z1 \
                                and float(zh.max()) >= z0:
                            nds |= src
                out = frozenset(nds)
            elif len(col):
                w = self.W[prof]
                js = self._samples(w, self._ring(np.unique(col), int(math.ceil(ATTACK_REACH / CELL))))
                js = js[(w.reg[js] >= 0) & (w.z[js] <= float(zh.max()) + 1.0) & (w.z[js] >= float(zl.min()) - 3.0)]
                out = frozenset(w.reg[js].tolist())
        self._padc[(atom, prof)] = out
        return out

    # ---- a point -> its node
    def map_point(self, prof, p, dz_max=30.0, gates=False):
        """(node or None, how, dz) for a world point (in memory); with
        ``gates`` a fourth value: the gates whose members alone cut the point
        off from its floor.  The point must lie in its floor sample's own air
        gap, and in the logic profile the straight segment from the sample
        to the point must be free of solids in the body band.  A point with
        no floor but within PICK_STAND over a slippery slope is ``slide``:
        touched sliding down it from the region at its top (AZ-359)."""
        lv, w, wg = self.lv, self.W[prof], self.wg
        c0 = int(lv.col(p[0], p[1]))
        cands = []
        for dx in (0, 1, -1, 2, -2):
            for dy in (0, 1, -1, 2, -2):
                a, n = lookup(w.u, w.a, w.c, np.array([c0 + dx + dy * lv.NX]))
                for k in range(int(n[0])):
                    j = int(a[0]) + k
                    r = int(w.reg_soft[j])
                    dz = p[2] - w.z[j]
                    if r < 0 or dz < -0.5 or dz > dz_max or w.ceil[j] < p[2] - 0.25:
                        continue
                    cands.append(((round(max(dz, 0.0), 1), abs(dx) + abs(dy)), r, dz, j))
        through = []
        best = None
        if cands:
            if prof == "logic":
                js = np.array([c_[3] for c_ in cands])
                blocked = self._segment_blocked(self.spans, p, js)
                free = [c_ for c_, b_ in zip(cands, blocked.tolist()) if not b_]
                if free:
                    best = min(free)
                elif gates:
                    opts = []
                    for g in self.gates + self.doors:
                        if not self._gate_near(g, p):
                            continue
                        bl = self._segment_blocked(g["_vspans"], p, js)
                        fr = [c_ for c_, b_ in zip(cands, bl.tolist()) if not b_]
                        if fr:
                            opts.append((min(fr), g["id"]))
                    if opts:
                        best, gid = min(opts)
                        through = [gid]
                if best is None:
                    self.walled_points = getattr(self, "walled_points", 0) + 1
            else:
                best = min(cands)
        lab, _ = wg.at(np.array([c0]), np.array([p[2] - 0.25]), np.array([p[2] + 0.25]))
        lab = int(lab[0])
        if best is not None and best[2] <= PICK_STAND:
            out = (best[1], "floor", best[2])
        elif lab >= 0:
            out, through = (w.nreg + lab, "swim", None), []
        elif lab == -2:
            out, through = (None, "kill-field", None), []
        elif best is not None:
            out = (best[1], ("jump" if best[2] <= PICK_STAND + 2.5 else "air"), best[2])
        else:
            through = []
            k = self.slopes.under(p, PICK_STAND)
            top = self.slopes.top(w, k) if k >= 0 else None
            hz = self.hazard_floor(prof, p) if top is None else None
            if top is not None:     # on a slope (AZ-359): touched sliding down from the region at its top
                out = (top, "slide", p[2] - float(self.slopes.sz[k]))
            elif hz is not None:
                out = (None, "in-hazard", hz[0])
            elif cands:
                out = (None, "walled", None)
            else:
                out = (None, "unplaced", None)
        return out + (through,) if gates else out

    def _segment_blocked(self, spans, p, js):
        """For logic floor samples js: is a solid span in the body band (the
        walking step .. max(the point, 1.5 m)) on the straight segment from
        the sample to p (0.1 m steps, the sample's own column left out,
        stopping ITEM_SHORT_M short of p)?"""
        w, lv = self.W["logic"], self.lv
        climb = w.p["climb"]
        xa, ya, za = w.x[js], w.y[js], w.z[js]
        d = np.hypot(p[0] - xa, p[1] - ya)
        dl = np.maximum(d - ITEM_SHORT_M, 0.0)
        ns = np.clip(np.ceil(dl / 0.1).astype(np.int64) + 1, 2, 400)
        pid = np.repeat(np.arange(len(js)), ns)
        k = np.arange(len(pid)) - np.repeat(np.cumsum(ns) - ns, ns)
        t = k / (ns[pid] - 1) * (dl / np.maximum(d, 1e-9))[pid]
        cols = lv.col(xa[pid] + t * (p[0] - xa[pid]), ya[pid] + t * (p[1] - ya[pid]))
        m = cols != w.col[js][pid]
        lo = (za + climb)[pid]
        hi = np.maximum(p[2], za + 1.5)[pid]
        hit = np.zeros(len(pid), dtype=bool)
        hit[m] = _hits(spans, cols[m], lo[m], hi[m])
        out = np.zeros(len(js), dtype=bool)
        np.logical_or.at(out, pid, hit)
        return out

    def _gate_near(self, g, p, pad=1.0):
        """Does a gate member present at load (a solid now) have p inside its (padded) box?"""
        if g.get("_vspans") is None:
            return False
        for oi, pres in zip(g["members"], g["present_at_load"]):
            if not pres or self.lv.owners[oi]["cat"] not in (CAT_TOGGLE, CAT_RIG):
                continue
            bb = self._bbox(oi)
            if bb is not None and bb[0] - pad <= p[0] <= bb[1] + pad and bb[2] - pad <= p[1] <= bb[3] + pad \
                    and bb[4] - pad <= p[2] <= bb[5] + pad:
                return True
        return False

    def _bbox(self, oi):
        if oi not in self._bbc:
            t = self.lv.tris_of(oi)
            if not len(t):
                self._bbc[oi] = None
            else:
                P = self.lv.P[t].reshape(-1, 3)
                self._bbc[oi] = (P[:, 0].min(), P[:, 0].max(), P[:, 1].min(), P[:, 1].max(), P[:, 2].min(), P[:, 2].max())
        return self._bbc[oi]

    def enclosed_by(self, p):
        """The gates (members present at load, solid) whose member mesh
        encloses p: ray-crossing parity odd on at least 4 of 7 rays."""
        out = []
        dirs = np.array([(1, 0, 0), (0, 1, 0), (0, 0, 1), (-1, 0, 0), (0, -1, 0), (0, 0, -1), (0.6, 0.8, 0.0)], dtype=float)
        for g in self.gates + self.doors:
            for oi, pres in zip(g["members"], g["present_at_load"]):
                if not pres or self.lv.owners[oi]["cat"] not in (CAT_TOGGLE, CAT_RIG):
                    continue
                bb = self._bbox(oi)
                if bb is None or not (bb[0] <= p[0] <= bb[1] and bb[2] <= p[1] <= bb[3] and bb[4] <= p[2] <= bb[5]):
                    continue
                T_ = self.lv.P[self.lv.tris_of(oi)]
                v0, e1, e2 = T_[:, 0], T_[:, 1] - T_[:, 0], T_[:, 2] - T_[:, 0]
                s_ = np.asarray(p, dtype=float) - v0
                odd = 0
                for d in dirs:
                    d = d / np.linalg.norm(d)
                    h = np.cross(np.broadcast_to(d, e2.shape), e2)
                    a = (e1 * h).sum(1)
                    ok = np.abs(a) > 1e-12
                    f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
                    u = f * (s_ * h).sum(1)
                    q = np.cross(s_, e1)
                    v = f * (q * d).sum(1)
                    tt = f * (e2 * q).sum(1)
                    odd += int((ok & (u >= 0) & (u <= 1) & (v >= 0) & (u + v <= 1) & (tt > 1e-6)).sum()) % 2
                if odd >= 4 and g["id"] not in out:
                    out.append(g["id"])
        return out

    def hazard_floor(self, prof, p):
        """(dz, owner) of a floor removed from the walk because the body there
        stands in a damage volume, under the point within 2 cells, or None."""
        w, lv = self.W[prof], self.lv
        if not len(w.hz_col):
            return None
        if not hasattr(w, "_hzc"):
            w._hzc = collections.defaultdict(list)
            for k, c in enumerate(w.hz_col.tolist()):
                w._hzc[c].append(k)
        c0 = int(lv.col(p[0], p[1]))
        best = None
        for dx in (0, 1, -1, 2, -2):
            for dy in (0, 1, -1, 2, -2):
                for k in w._hzc.get(c0 + dx + dy * lv.NX, ()):
                    dz = p[2] - float(w.hz_z[k])
                    if -0.5 <= dz <= PICK_STAND + 2.5 and w.hz_ceil[k] >= p[2] - 0.25 and (best is None or dz < best[0]):
                        best = (dz, int(w.hz_own[k]))
        return best

    def footprint(self, oi, prof="logic"):
        """Nodes whose body overlaps an owner's mesh (land: a sample within
        one cell; water: a swim column of the mesh): node -> samples."""
        lv, w = self.lv, self.W[prof]
        col, zlo, zhi, _ = raster(lv, lv.tris_of(oi))[:4]
        if not len(col):
            return {}
        H = w.p["height"]
        nds = collections.Counter()
        cc = np.concatenate([col + dx + dy * lv.NX for dx in (-1, 0, 1) for dy in (-1, 0, 1)])
        lo = np.concatenate([zlo] * 9)
        hi = np.concatenate([zhi] * 9)
        a, n = lookup(w.u, w.a, w.c, cc)
        for k in range(w.mx):
            v = k < n
            j = np.where(v, a + k, 0)
            ok = v & (w.reg_soft[j] >= 0) & (w.z[j] <= hi + 0.25) & (w.z[j] + H >= lo - 0.25) & (w.ceil[j] > lo)
            nds.update(w.reg_soft[j[ok]].tolist())
        lab, _ = self.wg.at(col, zlo, zhi)
        nds.update((w.nreg + lab[lab >= 0]).tolist())
        return {int(x): int(c) for x, c in nds.items()}

    def footprint_or_near(self, oi, prof="logic"):
        nds = self.footprint(oi, prof)
        if nds:
            return sorted(nds, key=lambda x: (-nds[x], x)), "geometry", None   # most overlap first
        P = self.lv.P[self.lv.tris_of(oi)].reshape(-1, 3)
        c = (float(P[:, 0].mean()), float(P[:, 1].mean()), float(P[:, 2].min()))
        r, how, dz = self.map_point(prof, c)
        if r is None:
            return [], how, None
        return [r], ("modelled" if how in ("floor", "swim", "slide") else "probe-needed"), dz

    def place_point(self, prof, p):
        """(node, how) for a spot, a teleport destination or an arrival: its
        walk sample within 30 m below (map_point), else a fall straight down
        onto the highest walk sample (at most 1 m above the spot) or water
        under it within 2 cells, unless the fall is lethal."""
        m = self.map_point(prof, p)
        if m[0] is not None:
            return m[0], m[1]
        w, lv = self.W[prof], self.lv
        c0 = int(lv.col(p[0], p[1]))
        best = None
        for dx in (0, 1, -1, 2, -2):
            for dy in (0, 1, -1, 2, -2):
                a, c = lookup(w.u, w.a, w.c, np.array([c0 + dx + dy * lv.NX]))
                for q in range(int(c[0])):
                    j_ = int(a[0]) + q
                    if w.reg_soft[j_] >= 0 and w.z[j_] <= p[2] + 1.0 and (best is None or w.z[j_] > best[1]):
                        best = (int(w.reg_soft[j_]), float(w.z[j_]))
        lab, top = self.wg.at(np.array([c0]), np.array([-1e5]), np.array([p[2]])) if self.wg.n else (np.array([-1]), None)
        if lab[0] >= 0 and (best is None or top[0] > best[1]):
            if p[2] - float(top[0]) >= LETHAL_FALL_M:
                return None, (f"over water {p[2] - float(top[0]):.0f} m below (a lethal fall: the rule applies at the "
                              f"water contact, skips-b F2)")
            return w.nreg + int(lab[0]), f"falls {max(p[2] - float(top[0]), 0.0):.0f} m into the water below"
        if best is not None:
            if p[2] - best[1] >= LETHAL_FALL_M:
                return None, f"over a floor {p[2] - best[1]:.0f} m below (a lethal fall)"
            return best[0], f"falls {max(p[2] - best[1], 0.0):.0f} m straight down"
        return None, "unplaced"

    # ---- teleports and rides (data: the wiring and the link curves)
    def teleport_edges(self):
        """Every playerLocation whose ``teleport`` plug is linked: per
        alternative of its decoded condition, an edge from the nodes
        touching the alternative's pulse pad (one no latch holds; the other
        pads are flags) to the playerLocation's own spot.  Confidence data."""
        lv, wire = self.lv, self.wire
        self.tele = []
        gen_locs = {x for t in self.gen.get("teleporters", []) for x in t["locators"]}
        for G, g in enumerate(lv.graphs):
            for r, ty in enumerate(g.types):
                if ty != "playerLocation" or g.recs[r] is None or not wire.links_into(G, r, "teleport"):
                    continue
                gid = f"{self.name}/g{G}/r{r}"
                alts = wire.terms(wire.value(G, r, "teleport").on)
                ent = {"spot": gid, "name": g.names[r], "in_generated_teleporters": gid in gen_locs,
                       "alternatives": None if alts is None else len(alts), "edges": 0}
                self.tele.append(ent)
                if not alts:
                    ent["none"] = "undecoded" if alts is None else "never fires"
                    continue
                p = lv.rec_points(gid)[0][0]
                for prof in DERIVED:
                    dst, how = self.place_point(prof, p)
                    if prof == "logic":
                        ent["destination"] = how
                    if dst is None:
                        continue
                    for pads, items in alts:
                        trig = [x for x in pads if x.split(":")[0] in self.PAD_KINDS]
                        for tp in [x for x in trig if x not in wire.latched] or trig:
                            base = {"kind": "teleport", "conf": "data", "ranks": [0, 0, 0, 0], "teleporter": gid,
                                    "why": f"touch {self.flagdef_label(tp)} -> playerLocation {g.names[r]}.teleport (wiring)"}
                            if pads - {tp}:
                                base["flags"] = sorted(pads - {tp})
                            if items:
                                base["needs"] = sorted(items)
                            for a_ in sorted(self.pad_nodes(tp, prof)):
                                if a_ != dst:
                                    self.E[prof][(a_, dst)].append(dict(base))
                                    ent["edges"] += prof == "logic"

    def rig_motion(self, oi):
        """The stops of a moved platform, one per mover (the record whose links
        move its ancestors' translate plugs): [(world displacement, the
        decoded condition that moves it or None, cycles, [mover])], from a
        timer's currentTime through the link's curve (its end value, or the
        farthest for a repeating timer), or a switch / damper / combiner
        output from 0 to 1; None when a rotation or scale moves it or a source
        is not decoded."""
        lv, wire = self.lv, self.wire
        o = lv.owners[oi]
        if o["kind"] != "platform" or o["approx"]:
            return None
        G, R = o["G"], o["R"]
        g = lv.graphs[G]
        per = {}
        for anc in g.ancestors(R):
            for k, lk in wire.incoming(G, anc):
                pn = g.plug_name(anc, lk.dst_plug)
                if pn not in collision.TRS_PLUGS:
                    continue
                if not pn.startswith("translate"):
                    return None
                src, st = lk.src, g.types[lk.src]
                sp = g.plug_name(src, lk.src_plug)
                ent = per.setdefault(src, {"dv": np.zeros(3), "conds": [], "cyc": False, "name": g.names[src]})
                cyc = False
                try:
                    cv = L.link_curve(g, src, k)

                    def gf(x, cv=cv, lk=lk):
                        return L.link_value(cv, x, lk.weight, lk.factor)
                    if st == "timer" and sp == "currentTime":
                        ta = wire.attrs(G, src)
                        t0, t1 = ta.get("startTime", 0.0), ta.get("stopTime", 0.0)
                        tc = ta.get("currentTime", t0)
                        rep = ta.get("repeat", 0.0) != 0.0
                        ts = [t0 + (t1 - t0) * q / 48.0 for q in range(49)] if t1 > t0 else [t0]
                        v0 = gf(tc)
                        vals = [gf(t) for t in ts]
                        vend = max(vals, key=lambda v: abs(v - v0)) if rep else gf(t1)
                        delta = vend - v0
                        E_ = wire.value(G, src, "enable")
                        cond = F_TRUE if (E_.init is not None and E_.init != 0.0) else E_.on
                        cyc = cyc or rep
                    elif st in ("switch", "damper", "combiner"):
                        s_ = wire.value(G, src, sp)
                        if s_.init is None:
                            return None
                        delta = (gf(1.0) - gf(0.0)) * (1.0 if s_.init == 0.0 else -1.0)
                        cond = s_.on if s_.init == 0.0 else s_.off
                    else:
                        return None
                except (ValueError, struct.error):
                    return None
                par = g.parent(anc)
                m = g.world(par)[0] if par is not None else nodes.IDENTITY
                vec = {"translateX": (1.0, 0.0, 0.0), "translateY": (0.0, 1.0, 0.0), "translateZ": (0.0, 0.0, 1.0)}[pn]
                ent["dv"] += np.array(nodes.apply(m, tuple(delta * x for x in vec))) - np.array(nodes.apply(m, (0.0, 0.0, 0.0)))
                ent["conds"].append(cond)
                ent["cyc"] = ent["cyc"] or cyc
        if not per:
            return None
        return [(e["dv"], wire.terms(f_and(*e["conds"])), e["cyc"], [e["name"]]) for _, e in sorted(per.items())]

    def ride_edges(self):
        """Rides on moved platforms whose motion is decoded (rig_motion): the
        walk regions beside the deck at rest (within RIG_RING cells of its
        footprint, floor within 0.6 m of the deck's top) join those beside it
        at the moved pose, one way (both ways when it cycles), with the
        decoded condition that starts it.  Confidence modelled."""
        lv = self.lv
        self.rides = []
        for o in lv.owners:
            if o["kind"] != "platform" or o["cat"] != CAT_RIG or not o["moved"] or o["approx"]:
                continue
            t = np.nonzero((lv.tri_owner == o["oi"]) & (lv.tri_nz >= envelope.STEP_NORMAL_Z))[0]
            deck = float(lv.tri_area[t].sum())
            if not (RIG_DECK_M2[0] <= deck <= RIG_DECK_M2[1]):
                continue
            for dv, alts, cyc, movers in self.rig_motion(o["oi"]) or ():
                self._ride(o, t, deck, dv, alts, cyc, movers)

    def _ride(self, o, t, deck, dv, alts, cyc, movers):
        lv = self.lv
        moved = float(np.linalg.norm(dv))
        if moved < 1.0 or not alts:
            if alts is None or moved >= 1.0:
                self.rides.append({"name": o["name"], "movers": movers[:4], "decoded": alts is not None,
                                   "moved_m": [round(float(np.hypot(dv[0], dv[1])), 1), round(float(dv[2]), 1)],
                                   "edges": 0, "note": "its start condition is not decoded" if alts is None else "never moves"})
            return
        P = lv.P[t].reshape(-1, 3)
        ztop = float(P[:, 2].max())
        ent = {"name": o["name"], "movers": movers[:4], "decoded": True, "cycles": bool(cyc), "deck_m2": round(deck, 1),
               "moved_m": [round(float(np.hypot(dv[0], dv[1])), 1), round(float(dv[2]), 1)],
               "requires": self.alts_req(alts), "edges": 0}
        self.rides.append(ent)
        for prof in DERIVED:
            w = self.W[prof]
            ends = []
            for shift, ring, tol in ((np.zeros(3), RIG_RING, 0.6), (dv, 2 * RIG_RING, 1.0)):
                # [proposal] at the stop the decoded pose is looser (the curve's end, not a measured stop): 2 m and 1 m
                cols = np.unique(lv.col(P[:, 0] + shift[0], P[:, 1] + shift[1]))
                js = self._samples(w, self._ring(cols, ring))
                js = js[(w.reg[js] >= 0) & (np.abs(w.z[js] - (ztop + shift[2])) <= tol)] if len(js) else js
                ends.append(set(w.reg[js].tolist()))
            if prof == "logic":
                ent["rest_regions"], ent["moved_regions"] = len(ends[0]), len(ends[1])
            edges = {}
            base = {"kind": "rig", "conf": "modelled", "ranks": [0, 0, 0, 0], "via": o["name"], "dh": float(dv[2]),
                    "why": f"ride {o['name']} (moved {float(np.hypot(dv[0], dv[1])):.1f} m across and {float(dv[2]):+.1f} m "
                           f"by {', '.join(movers[:2])}: decoded from its link curves)"}
            for x_, y_ in [(0, 1)] + ([(1, 0)] if cyc else []):
                for a_ in ends[x_]:
                    for b_ in ends[y_]:
                        if a_ != b_ and not (a_ in ends[y_] and b_ in ends[x_]):
                            self._alt_edges(edges, a_, b_, base, alts, "started by")
            for k_, es in self._flat(edges).items():
                self.E[prof][k_].extend(es)
                ent["edges"] += len(es) if prof == "logic" else 0

    # ---- anchors, spawn and events
    HINT_NAMES = re.compile(r"\b(touch|actionButton|magic|key|whack|joystickOn)\(([^()]+)\)")

    def anchors(self):
        """Every anchor's nodes per profile (exits by their trigger meshes,
        save points, keylocks, seals, obsidian locks, spots, keylords,
        barriers): ``obj_at`` (logic) and ``anchor[prof]`` (node -> ids)."""
        lv, gen = self.lv, self.gen
        self.anchor = {prof: collections.defaultdict(list) for prof in DERIVED}
        self.obj_at = {}

        def put(kind, gid, label, names=None, points_gid=None):
            for prof in DERIVED:
                nds, how, dz = [], None, None
                for nm in names or []:
                    for oi in lv.by_name.get(nm, []):
                        n_, h_, d_ = self.footprint_or_near(oi, prof)
                        if n_:
                            nds += n_
                            how = h_ if how is None or h_ == "geometry" else how
                            dz = d_
                rig = any(lv.owners[oi]["moved"] or lv.owners[oi]["approx"] for nm in names or []
                          for oi in lv.by_name.get(nm, []))
                if not nds and points_gid:
                    r, h_, d_ = self.map_point(prof, lv.rec_points(points_gid)[0][0], dz_max=6.0)
                    if r is not None:
                        nds, how, dz = [r], ("geometry" if h_ in ("floor", "swim", "slide") else "probe-needed"), d_
                ent = {"kind": kind, "id": gid, "label": label, "nodes": sorted(set(nds)), "how": how or "unplaced",
                       "rig": rig}
                if nds:
                    ent["main"] = nds[0]      # the node the trigger overlaps most (the first owner's)
                if dz is not None:
                    ent["dz"] = round(dz, 1)
                if not ent["nodes"] and points_gid and prof == "logic":
                    sup = self.support(lv.rec_points(points_gid)[0][0])
                    if sup:
                        ent["support"] = sup
                for n_ in ent["nodes"]:
                    self.anchor[prof][n_].append(gid)
                if prof == "logic":
                    self.obj_at[gid] = ent

        def owner_name(gid):
            oi = lv.by_rec.get(_rec(gid))
            return [lv.owners[oi]["name"]] if oi is not None else []

        for e in gen.get("exits", []):
            put("exit", e["id"], f"{e['name']} -> {e['dest_level']}", [m[1] for m in self.HINT_NAMES.findall(e["gate_hint"] or "")])
        for s in gen.get("save_points", []):
            put("save_point", s["id"], s["save_id"], [m[1] for m in self.HINT_NAMES.findall(s.get("do_save") or "")], s["id"])
        for k in gen.get("keylocks", []):
            if k.get("trigger"):            # e5's relays have no trigger platform of their own
                put("keylock", k["id"], k["namespace"], owner_name(k["trigger"]))
        for s in gen.get("seals", []):
            put("seal", s["id"], s["name"], [n for t in s.get("touch") or [] for n in owner_name(t.split()[0])])
        for ol in gen.get("obsidian_locks", []):
            hints = [b["hint"] for b in self.blockers.values() if b.get("bound_to") == f"obsidian_lock:{ol['id']}"]
            put("obsidian_lock", ol["id"], f"lock {ol['lock']}",
                sorted({m[1] for h in hints for m in self.HINT_NAMES.findall(h)}), ol["open_combiner"])
        for s in gen.get("spots", []):
            put("spot", s["id"], s["name"], None, s["id"])
        for k in gen.get("keylords", []):
            if k.get("keylord"):
                put("keylord", k["id"], k["namespace"], None, k["keylord"])
        for b in gen.get("barriers", []):
            put("barrier", b["id"], b["name"], [n for sid in b["shapes"] for n in owner_name(sid)])

    def support(self, p):
        """What a point stands on (in memory): the highest present solid span
        top at most 3 m below it in its column, its owner's name and
        category, and the gate the owner belongs to."""
        lv, sp = self.lv, self.spans
        a, n = sp.range_of(np.array([int(lv.col(p[0], p[1]))]))
        best = None
        for k in range(int(n[0])):
            s_ = int(a[0]) + k
            dz = p[2] - float(sp.top[s_])
            if -0.5 <= dz <= 3.0 and (best is None or dz < best[0]):
                best = (dz, s_)
        if best is None:
            return None
        oi = int(lv.tri_owner[sp.toptri[best[1]]])
        o = lv.owners[oi]
        gate = next((g["id"] for g in getattr(self, "gates", []) if oi in g["members"]), None)
        return {"owner": o["name"] if o["kind"] == "platform" else "(static level mesh)", "category": CAT_NAME[o["cat"]],
                "oi": oi, "dz": round(best[0], 1), "gate": gate,
                "gate_requires": next((g["requires"] for g in self.gates if g["id"] == gate), None) if gate else None}

    def spawn_spots(self):
        """(the first-visit spawn spot ids, every arrival spot id of a live exit into this level)."""
        arrivals = {e["arrival"] for _, e in self.exits_into if e.get("arrival") and e.get("live")}
        names = {s["name"]: s["id"] for s in self.gen.get("spots", [])}
        first = SPAWN.get(self.name, ["startspot"])
        missing = [n for n in first if n not in names]
        if missing:
            raise ValueError(f"{self.name}: spawn spots not in its generated data: {missing}")
        return [names[n] for n in first], sorted(arrivals)

    def _deck_regions(self, prof, oi, z, ring_cells=RIG_RING, tol=0.5, shift=(0.0, 0.0)):
        lv, w = self.lv, self.W[prof]
        tri = np.nonzero((lv.tri_owner == oi) & (lv.tri_nz >= envelope.STEP_NORMAL_Z))[0]
        if not len(tri):
            return set()
        P = lv.P[tri].reshape(-1, 3)
        js = self._samples(w, self._ring(np.unique(lv.col(P[:, 0] + shift[0], P[:, 1] + shift[1])), ring_cells))
        js = js[(w.reg[js] >= 0) & (np.abs(w.z[js] - z) <= tol)] if len(js) else js
        return set(w.reg[js].tolist())

    def resolve_spot(self, prof, sid):
        """(nodes, how) for a spawn or arrival spot the anchors leave
        unplaced (defaults taken under D115): a spot on a moved platform
        rides it (the walk regions beside its deck at rest and at its decoded
        stop); a spot on a surface the walk does not stand on settles onto
        the walk within RIDE_RING_M at its height [verified xemu, 70 of 70
        arrivals settled within 0.1-6.4 m]; one on a slippery slope slides
        down its fall line (:class:`~.moves.Slopes`, AZ-359); any other
        falls straight down (place_point)."""
        p = self.lv.rec_points(sid)[0][0]
        sup = self.support(p)
        if sup and sup["category"] == "rig":
            oi = sup["oi"]
            regs = self._deck_regions(prof, oi, p[2])
            per = {}
            for dv, _, _, movers in self.rig_motion(oi) or ():
                rs = self._deck_regions(prof, oi, p[2] + float(dv[2]), int(RIDE_RING_M / CELL), RIDE_DZ_M,
                                        (float(dv[0]), float(dv[1])))
                per[f"{', '.join(movers[:2])} {float(dv[2]):+.1f} m"] = len(rs)
                regs |= rs
            if regs:
                return sorted(regs), (f"stands on rig {sup['owner']}: rides it; the walk regions beside its deck at rest "
                                      f"and at its decoded stop {per}; {len(regs)} regions in all")
        if sup:
            w, lv = self.W[prof], self.lv
            js = self._samples(w, self._ring(np.array([int(lv.col(p[0], p[1]))]), int(RIDE_RING_M / CELL)))
            js = js[(w.reg[js] >= 0) & (np.abs(w.z[js] - (p[2] - sup["dz"])) <= RIDE_DZ_M)] if len(js) else js
            if len(js):
                return sorted(set(w.reg[js].tolist())), (f"stands on {sup['owner']} ({sup['category']}, not a logic "
                                                         f"floor): settles onto the walk within {RIDE_RING_M:g} m at "
                                                         f"its height")
        k = self.slopes.under(p, 3.0)
        if k >= 0:      # on a slope (AZ-359): it slides down the fall line
            x, y, z, k, path = self.slopes.follow(k)
            land = self.slopes.landing(self.W[prof], self.wg, x, y, z, k)
            if land is not None:
                return [land[0]], f"stands on a slippery slope: slides {path * CELL:.1f} m down its fall line"
        r, how = self.place_point(prof, p)
        return ([r], how) if r is not None else ([], f"unresolved: {how}")

    def spawn_nodes(self):
        """The spawn's nodes: the first spots' anchors; a spawn or arrival
        spot left unplaced is resolved (resolve_spot) and its anchor takes
        the resolved nodes (how probe-needed)."""
        first, arrivals = self.spawn_spots()
        self.spawn_ids = (first, arrivals)
        self.spawn_how = {}
        for sid in sorted(set(first) | set(arrivals)):
            ent = self.obj_at.get(sid)
            if ent is None:
                continue
            if ent["nodes"]:
                self.spawn_how[sid] = {"logic": "anchor (the spot's own mapping)"}
                continue
            nds, how = self.resolve_spot("logic", sid)
            self.spawn_how[sid] = {"logic": how}
            if nds:
                ent["nodes"], ent["main"], ent["how"] = sorted(set(nds)), nds[0], "probe-needed"
                ent.pop("support", None)
                for n_ in ent["nodes"]:
                    self.anchor["logic"][n_].append(sid)
        self.spawn = {"logic": sorted({n_ for sid in first for n_ in self.obj_at.get(sid, {}).get("nodes", [])})}
        st = []
        for sid in first:
            p = self.lv.rec_points(sid)[0][0]
            sup = self.support(p)
            r = self.map_point("phys", p, 6.0)[0]
            if (sup and sup["category"] == "rig") or r is None:
                nds, how = self.resolve_spot("phys", sid)
                st += nds
                self.spawn_how.setdefault(sid, {})["phys"] = how
            else:
                st.append(r)
        self.spawn["phys"] = sorted(set(x for x in st if x is not None))

    def flag_nodes(self):
        """The setter of every flag an edge, a gate or a door uses: the nodes
        whose body touches the pad, a pickup's location, or an arrival at
        the spawn; a pad whose latch is in the level's save list stays set on
        a later visit (``persistent``)."""
        atoms = set()
        for prof in DERIVED:
            for es in self.E[prof].values():
                for e in es:
                    atoms.update(e.get("flags", ()))
        for g in self.gates:
            for pads, _ in g.get("alts") or ():
                atoms.update(pads)
        first = set(self.spawn_ids[0])
        saved = {}
        for at in sorted(atoms):
            kind, _, rest = at.partition(":")
            ent = {"kind": kind, "label": self.flag_label(at)}
            persist = False
            for G_, r_ in self.wire.latch_of.get(at, ()):
                if G_ not in saved:
                    saved[G_] = saved_names(self.lv.graphs[G_])
                persist = persist or self.lv.graphs[G_].names[r_] in saved[G_]
            ent["persistent"] = persist
            if kind == "loc":
                ent["loc"] = rest
            elif kind == "arrive":
                G, R = (int(x) for x in rest.split(":"))
                ent["spawn"] = f"{self.name}/g{G}/r{R}" in first
            else:
                G, R = (int(x) for x in rest.split(":"))
                ent["platform"] = self.lv.graphs[G].names[R]
            ent["nodes"] = {prof: self.pad_nodes(at, prof) for prof in DERIVED}
            self.flagdef[at] = ent

    # ---- zones: strongly connected under free movement (safe tier, no item, no gate)
    def zones(self):
        w = self.W["logic"]
        n = w.nreg + self.wg.n
        ia, ib = [], []
        for (a, b), es in self.E["logic"].items():
            if any(free_edge(e) for e in es):
                ia.append(a)
                ib.append(b)
        lab = _strong_components(n, np.array(ia, dtype=np.int64), np.array(ib, dtype=np.int64))[1]
        area = np.concatenate((w.reg_count * CELL * CELL, self.wg.count * CELL * CELL if self.wg.n else np.zeros(0)))
        za = np.bincount(lab, weights=area)
        first = np.full(len(za), n)
        np.minimum.at(first, lab, np.arange(n))
        order = np.lexsort((first, -za))
        remap = np.empty(len(za), dtype=np.int64)
        remap[order] = np.arange(len(za))
        self.zone_of = remap[lab]
        self.nzone = len(za)
        self.zone_area = za[order]

    # ---- reach over the region graph
    def _adj(self, prof):
        adj = collections.defaultdict(list)
        for (a, b), es in self.E[prof].items():
            for e in es:
                adj[a].append((b, e))
        return adj

    @staticmethod
    def items_ok(items, gates_open, air):
        """Item atoms (§5.1 strings, each a conjunction): an ``air>=N`` part
        holds at air level >= N, any other part only with the gates open."""
        for it in items:
            for part in it.split("&"):
                m = re.fullmatch(r"air>=(\d+)", part.strip().strip("()"))
                if m:
                    if int(m.group(1)) > air:
                        return False
                elif not gates_open:
                    return False
        return True

    def gate_ok(self, gid, gates_open, fl, allow_probe, only_gate=None, air=3):
        if only_gate is not None and gid != only_gate:
            return False
        if gid in self.undecoded:
            return gates_open and "gate-undecoded" in allow_probe
        g = self.gate_by_id.get(gid)
        if g is None:
            return gates_open
        for pads, items in g.get("alts") or ():
            if (fl is None or pads <= fl) and self.items_ok(items, gates_open, air):
                return True
        return False

    def usable(self, e, ti, air, allow_probe, gates_open, only_gate=None, no_slip=False, fl=None):
        """Can edge e be taken at tier ti with air level <= air, the probe
        classes allow_probe, gates open or not?  An edge through a gate needs
        it passable; a ride's or teleport's items hold with the gates open;
        its pads (``flags``) must be set (fl None: all are)."""
        if e["ranks"][ti] > air:
            return False
        if e.get("through") and not all(self.gate_ok(t, gates_open, fl, allow_probe, only_gate, air) for t in e["through"]):
            return False
        if e.get("needs") and (only_gate is not None or not self.items_ok(e["needs"], gates_open, air)):
            return False
        if e.get("needs_undecoded") and (not gates_open or only_gate is not None or "gate-undecoded" not in allow_probe):
            return False
        if e.get("flags") and fl is not None and not fl.issuperset(e["flags"]):
            return False
        if no_slip and e.get("slip"):
            return False
        pc = probe_class(e)
        return pc is None or pc in allow_probe


def _rec(gid):
    _, gs, rs = gid.split("/")
    return int(gs[1:]), int(rs[1:])


def _strong_components(n, a, b):
    """(count, labels) of the strongly connected components of the directed
    graph on n nodes with edges a[k] -> b[k] (Tarjan's algorithm, iterative)."""
    order = np.lexsort((b, a))
    a, b = np.asarray(a, dtype=np.int64)[order], np.asarray(b, dtype=np.int64)[order]
    start = np.searchsorted(a, np.arange(n + 1)).tolist()
    succ = b.tolist()
    index, low, onstack, comp = [-1] * n, [0] * n, [False] * n, [-1] * n
    stack, c, counter = [], 0, 0
    for v0 in range(n):
        if index[v0] >= 0:
            continue
        index[v0] = low[v0] = counter
        counter += 1
        stack.append(v0)
        onstack[v0] = True
        work = [(v0, start[v0])]
        while work:
            v, i = work[-1]
            if i < start[v + 1]:
                work[-1] = (v, i + 1)
                w_ = succ[i]
                if index[w_] < 0:
                    index[w_] = low[w_] = counter
                    counter += 1
                    stack.append(w_)
                    onstack[w_] = True
                    work.append((w_, start[w_]))
                elif onstack[w_]:
                    low[v] = min(low[v], index[w_])
                continue
            work.pop()
            if work:
                u = work[-1][0]
                low[u] = min(low[u], low[v])
            if low[v] == index[v]:
                while True:
                    w_ = stack.pop()
                    onstack[w_] = False
                    comp[w_] = c
                    if w_ == v:
                        break
                c += 1
    return c, np.array(comp, dtype=np.int64)


def _ball_pairs(q, pts, r):
    """(query index, point index) of every pair within r, in query order then point order."""
    qi, pj, _ = RadiusIndex(pts, r).pairs(q)
    return qi.tolist(), pj.tolist()

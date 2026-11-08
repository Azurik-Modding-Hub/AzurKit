"""Reach's gates: what a level's barriers, doors and hazards separate and
what opens them, and the crossings that bypass a shut one.

Part of the reach model (Step R1.3b; reach v6's gate methods), mixed into
:class:`~.reach.Reach`:

* :meth:`Gates.gate_groups`: every toggled solid, link-driven damage
  volume (with the drag currents its driver switches) and static damage
  volume (a ``hazard`` pseudo-gate whose protection is not decoded),
  grouped by driver.  A gate bound to a generated barrier, keylord, seal
  or obsidian lock takes its requirement; one in a blocker family with
  hand binds takes the family's own requirement when the family is
  monotone and bound to a known gate, and is held (undecoded) otherwise;
  any other is read from the wiring (:meth:`Gates.wire_gates`).
* :meth:`Gates.find_doors`: door-shaped rigs.  One whose movers trace
  back to a lock is that lock's gate; one whose movers' links decode is a
  wired gate (leaves on one mover are one gate); an undecoded one opened
  by the action button or a touch is a probe-needed action door.
* :meth:`Gates.gate_variant`: the region graph recut with a gate's
  members flipped gives the regions it separates (``merges``, and
  ``water_merges``), its ``gate`` edges, and ``destroy_from``.
* :meth:`Gates.resolve_overflights`, :meth:`Gates.resolve_hazard_flights`:
  a flight over a shut barrier is that gate's crossing; one whose only
  obstacle is one gate's damage volume is that gate's edge.
* :meth:`Gates.barrier_cut`: every connection between a gate's two sides
  that does not go through it needs a skip: a held generated skip
  ``<level>.bskip.<barrier>.<from>.<to>.<kit>`` (D113, D114) or a
  confirmed ``tricks.toml`` skip of that gate and direction.

Authoring only (numpy); coordinates stay in memory.
"""

from __future__ import annotations

import collections
import heapq
import math
import re

import numpy as np

from devkit.rando import physics
from azurkit.tools.randomizer.draft.floors import DERIVED, PROFILES, Walk, lookup
from devkit.rando.draft.flights import OVER_SIDE_M
from azurkit.tools.randomizer.draft.geometry import (
    CAT_DAMAGE, CAT_RIG, CAT_TOGGLE, CELL, Obstacles, RadiusIndex, Spans, raster)
from devkit.rando.draft.moves import WaterGrid
from azurkit.tools.randomizer.draft.wiring import F_FALSE, F_TRUE, RANK_REQ, TIER_N, TIERS, f_and, f_or, req_dnf
from azurkit.tools.randomizer.art import collision

ATTACK_REACH = 3.0      # [inferred] a barrier is hit from a sample within 3 m of its mesh
PICK_STAND = physics.PICK_STAND   # [inferred] a pickup up to 1.5 m above the floor is touched standing
GEO_SIDE_R = 30.0       # [proposal] a zone's samples within this of a barrier place it on a side of its plane
OVER_SIDE_R = 15.0      # [proposal] a side region's samples within this of the barrier's members place it
PROBE_LADDER = ("swim-exit", "climb", "push", "current", "teleport", "door", "rig", "lip", "hazard", "gate-undecoded", "bskip",
                "sweep", "float")
SKIP_CLASS = "skip"
# a crossing uses a confirmed skip's atom only when its own movement is in logic (a crossing on probe-needed movement
# keeps a held generated atom even in a confirmed direction)
CONFIRMABLE = ("geometry", "modelled")
# A confirmed bskip skip is used for the crossings of its gate in its direction, relative to the side that holds the
# spawn ("out": from the spawn's side; "in": into it), or by content where neither side holds it (the direction whose
# far side holds `to_location` or whose near side holds `from_location` / `from_anchor`); a confirmed bskip skip with no
# entry here is not used (fail closed)
CONFIRMED_BSKIP_SIDE = {
    "w1.firewall01_air2_beach_town": "out",
    "town.firewall02_air1": "in",
    "w1.firewall01_air1_beach_town": "out",
    "w1.firewall01_air1_town_beach": "in",
    "f1.flamespout6_air1": {"to_location": "f1/g0/r1399"},
    "e2.steam_group_air2": {"to_location": "e2/g0/r2955"},   # Step R1.8g: the L3 string's goal, power_fire's zone
    "e2.steam_group_air1": {"to_location": "e2/g0/r2955"},   # Step R1.31 (D277): X.15's L3 string, the same goal
}
# A current that blocks the way and the tricks.toml skip that names its crossing (in logic only once confirmed, D114):
# w1.shoreline_rollthrough is a roll chain on the floor across the push-12 TempPush band south of the bar, anchored at
# the w2-arrival shore (default taken under D115)
CURRENT_SKIPS = {"w1": [{"skip": "w1.shoreline_rollthrough", "volumes": ("TempPush6Shape",),
                         "anchors": ("W2_W1a", "W2_W1b")}]}
DOOR_DECK_M2, DOOR_FACE_M2, DOOR_HEIGHT_M = 1.5, 2.0, 1.8   # [inferred] a door: a standable deck under 1.5 m2, at
                                                           # least 2 m2 of near-vertical face, 1.8 m tall


def free_edge(e):
    """The zones' free movement: no item at the zone margins (a flight's
    ``zone_rank``, envelope.ZONE's fixed margins; any other edge's safe
    rank), no gate, confidence geometry or modelled, not a walk onto or off
    a near-flat slippery floor, no pad and not over a shut barrier."""
    return e["conf"] in ("geometry", "modelled") and e.get("zone_rank", e["ranks"][0]) == 0 and not e.get("through") \
        and not e.get("needs") and not e.get("slip") and not e.get("flags") and not e.get("over")


def probe_class(e):
    """The probe class an edge needs (None: none; ``skip``: a confirmed skip's)."""
    if e.get("skip_atom"):
        return SKIP_CLASS
    if e["conf"] != "probe-needed":
        return None
    if e.get("trick") == "bskip":
        return "bskip"       # a held barrier bypass, whatever its movement
    if e["kind"] in ("climb", "push", "teleport", "rig", "door", "current"):
        return e["kind"]
    if e.get("down"):
        return "push"        # a flight through a downdraft
    if e.get("haz") and not e.get("wall"):
        return "hazard"
    if e["kind"] == "swim":
        return "swim-exit"
    why = e.get("why", "")
    if "slippery" in why:
        return "slippery"
    return "lip" if "lip" in why else "sweep"


class Gates:
    """The gate methods of :class:`~.reach.Reach` (the module docstring)."""

    # ---- the gates
    def _gate_drv(self, o):
        """The gate group key (its driver) of a gate member, or None."""
        if o["kind"] != "platform":
            return None
        if o["cat"] == CAT_TOGGLE:
            plugs = ("gameSolid",)
        elif o["cat"] == CAT_DAMAGE and "damage" in o["driven"]:
            plugs = ("damage",)
        elif o["oi"] in self.drag_oids:
            plugs = ("pushEnable",)
        elif o["cat"] == CAT_DAMAGE and o["present"]:
            plugs = None    # a static hazard: a pseudo-gate, protection not decoded
        else:
            return None
        return (tuple(self.lv.driver_of(o["oi"], plugs)) if plugs else ("hazard:" + o["name"],)) or (o["name"],)

    def _over_groups(self):
        """Per gate group, its members that are a barrier while it is shut: a
        toggled solid present at load or a driven damage volume that is on
        (not a crumbling floor, a drag current or a static hazard)."""
        by = collections.defaultdict(list)
        for o in self.lv.owners:
            if not o["present"] or o["oi"] in self.crumble or o["oi"] in self.drag_oids:
                continue
            if not (o["cat"] == CAT_TOGGLE or (o["cat"] == CAT_DAMAGE and "damage" in o["driven"])):
                continue
            drv = self._gate_drv(o)
            if drv is not None and not drv[0].startswith("hazard:"):
                by[drv].append(o["oi"])
        return sorted(by.items(), key=lambda kv: min(kv[1]))

    def gate_groups(self):
        lv = self.lv
        by_drv = collections.defaultdict(list)
        for o in lv.owners:
            drv = self._gate_drv(o)
            if drv is not None:
                by_drv[drv].append(o["oi"])
        gen_barriers = {b["id"]: b for b in self.gen.get("barriers", [])}
        hand_of = {b["of"]: b["id"] for b in self.toml.get("barrier", [])}
        buttons = {}
        for b in self.toml.get("button", []):
            buttons.setdefault(b.get("of"), b["id"])
        gates = []
        for drv, oids in sorted(by_drv.items(), key=lambda kv: min(kv[1])):
            recs = [f"{self.name}/g{lv.owners[oi]['G']}/r{lv.owners[oi]['R']}" for oi in oids]
            bl = [self.blockers[r] for r in recs if r in self.blockers]
            fam = next((self.families[r] for r in recs if r in self.families), None)
            bound = sorted({b["bound_to"] for b in bl if b.get("bound_to")})
            g = {"driver": list(drv), "members": oids, "records": recs,
                 "member_names": [lv.owners[oi]["name"] for oi in oids],
                 "member_state": ["solid" if lv.owners[oi]["cat"] == CAT_TOGGLE else
                                  "drag current" if oi in self.drag_oids else "damage" for oi in oids],
                 "present_at_load": [bool(lv.owners[oi]["present"]) for oi in oids],
                 "bound_to": bound, "family": fam["family"] if fam else None,
                 "family_class": fam["class"] if fam else None}
            gid = req = None
            for bt in bound:
                kind, _, ref = bt.partition(":")
                if kind == "barrier" and ref in gen_barriers:
                    gid = hand_of.get(ref, f"{self.name}.{gen_barriers[ref]['name']}")
                    req = gen_barriers[ref]["requires"]
                    g["generated_barrier"] = ref
                    g["shapes"] = gen_barriers[ref]["shapes"]
                elif kind == "keylord":
                    req = f"event:{next((k['event'] for k in self.gen.get('keylords', []) if k['id'] == ref), ref)}"
                elif kind == "seal":
                    req = f"button:{buttons[ref]}" if ref in buttons else f"seal {ref}"
                elif kind == "obsidian_lock":
                    req = f"button:{buttons[ref]}" if ref in buttons else f"obsidian lock {ref}"
            if gid is None and drv and drv[0].startswith("hazard:"):
                stem = re.sub(r"[^A-Za-z0-9_]", "_", drv[0][len("hazard:"):].replace(":", "_"))
                gid = f"{self.name}.hazard.{stem}"
                g["hazard"] = {"damage": [lv.owners[oi]["attrs"].get("damage") for oi in oids],
                               "note": "a static damage volume the logic profile never walks through; what protects "
                                       "against it (an armour) is not decoded [inferred]"}
            if gid is None:
                stem = re.sub(r"[^A-Za-z0-9_]", "_", drv[0].split(":")[-1] if drv else "gate")
                gid = f"{self.name}.gate.{stem}"
            if req is None and fam and fam.get("hand"):
                # the family's own requirement (§5.1, atoms that resolve under §2.3), never its hand binds OR-ed; a
                # family that is not monotone or needs a probe is held: undecoded, opened only on the gate-undecoded rung
                freq = fam.get("requires")
                if fam.get("class") == "bound_to_known_gate" and fam.get("monotone") and isinstance(freq, str):
                    req = freq
                    g["requires_from_family"] = fam["family"]
                else:
                    g["family_held"] = (f"blocker family {fam['family']} is {fam.get('class')} (monotone "
                                        f"{fam.get('monotone')}): held until its probe settles it ({fam.get('probe') or 'no probe'})")
            g["id"], g["requires"] = gid, req
            while any(x["id"] == g["id"] for x in gates):
                g["id"] += "_"
            gates.append(g)
        return gates

    def wire_gates(self):
        """Every gate's alternatives [(pads, items)]: a data requirement as
        items; else the members' flipped state read from the wiring (OFF of a
        member there at load, ON of one absent), ANDed over the members.
        Undecoded stays None; a condition that never holds is false; a pad no
        logic node touches cannot be set, and a gate left with no
        alternative is undecoded (held), not never."""
        for g in self.gates:
            if g.get("alts") is not None:
                continue
            if g.get("family_held"):
                g["alts"] = None
                continue
            if g["requires"] is not None:
                f = req_dnf(g["requires"])
                g["alts"] = [(frozenset(), frozenset(x[2:] for x in t)) for t in f] if f is not None else None
                g["requires_from"] = "family" if g.get("requires_from_family") else "data"
                continue
            if g.get("hazard"):
                g["alts"] = None
                continue
            cond = F_TRUE
            for oi, pres, st in zip(g["members"], g["present_at_load"], g["member_state"]):
                plug = "gameSolid" if st == "solid" else "pushEnable" if st == "drag current" else "damage"
                sg = self.wire.plug(oi, plug)
                cond = f_and(cond, sg.off if pres else sg.on)
            alts = self.wire.terms(cond)
            if alts:
                live = [a for a in alts if all(p.split(":")[0] in ("arrive", "loc") or self.pad_nodes(p, "logic") for p in a[0])]
                if not live:
                    g["pads_unreached"] = sorted({self.flag_label(p) for a in alts for p in a[0]})
                    alts = None
                else:
                    alts = live
            g["alts"] = alts
            if alts is not None:
                g["requires"] = self.alts_req(alts)
                g["requires_from"] = "wiring"
                g["pad_only"] = bool(alts) and any(not items for _, items in alts)

    def lock_req(self, kind, x, hand):
        """A keylock's, seal's or obsidian lock's requirement: its hand button;
        an e5 relay (``relay_of`` names the coded locks whose LockToggle
        drives it) takes their buttons, ANDed; any other lock with no hand
        button fails closed (an undecoded marker)."""
        if x["id"] in hand:
            return f"button:{hand[x['id']]}"
        rel = [y for k_ in ("keylocks", "seals", "obsidian_locks") for y in self.gen.get(k_, [])
               if y.get("namespace") in (x.get("relay_of") or ())]
        if rel and len(rel) == len(x["relay_of"]) and all(y["id"] in hand for y in rel):
            b_ = [f"button:{hand[y['id']]}" for y in rel]
            return b_[0] if len(b_) == 1 else f"({' & '.join(b_)})"
        return f"<{kind[:-1]} {x['id']}: no hand button>"

    def rig_gating(self):
        """Tag the probe-needed rig rides whose mover a keylock, seal or
        obsidian lock drives out (generated ``drives_out``) with that
        button: the ride needs it (a lock with no hand button fails closed)."""
        hand = {b.get("of"): b["id"] for b in self.toml.get("button", [])}
        by_name = {}
        for kind in ("keylocks", "seals", "obsidian_locks"):
            for x in self.gen.get(kind, []):
                req = self.lock_req(kind, x, hand)
                for d in x.get("drives_out", []) or []:
                    by_name.setdefault(d.split(".")[0], req)
        for prof in DERIVED:
            for r in self.rig_info[prof]:
                g = sorted({by_name[m] for m in r["movers"] if m in by_name})
                if g:
                    r["gated_by"] = g
            gated = {r["name"]: r["gated_by"] for r in self.rig_info[prof] if r.get("gated_by")}
            for es in self.E[prof].values():
                for e in es:
                    if e["kind"] == "rig" and e.get("via") in gated and e["conf"] == "probe-needed":
                        e["gated_by"] = gated[e["via"]]
                        e["why"] += f"; started by {' | '.join(gated[e['via']])} (data: drives_out)"
                        ok_ = [a_ for a_ in e["gated_by"] if a_.startswith("button:")]
                        if len(ok_) == len(e["gated_by"]):
                            e["needs"] = [" | ".join(ok_)]
                        else:
                            e["needs_undecoded"] = list(e["gated_by"])

    def lock_map(self):
        """(graph, record) -> (requirement, lock id, label) for every keylock,
        seal and obsidian lock: its own record, trigger, lock toggle, open
        combiner or activate record, and the records its drives_out names."""
        lv = self.lv
        hand = {b.get("of"): b["id"] for b in self.toml.get("button", [])}
        names, out = {}, {}

        def rec(gid):
            _, gs, rs = gid.split("/")
            return int(gs[1:]), int(rs[1:])
        for kind in ("keylocks", "seals", "obsidian_locks"):
            for x in self.gen.get(kind, []):
                req = self.lock_req(kind, x, hand)
                lab = x.get("namespace") or x.get("name") or x["id"]
                G = rec(x["id"])[0]
                for f in ("id", "trigger", "lock_toggle", "open_combiner", "activate"):
                    if x.get(f):
                        out.setdefault(rec(x[f]), (req, x["id"], lab))
                if G not in names:
                    names[G] = collections.defaultdict(list)
                    for ri, nm in enumerate(lv.graphs[G].names):
                        names[G][nm].append(ri)
                for d in x.get("drives_out", []) or []:
                    for ri in names[G].get(d.split(".")[0], ()):
                        out.setdefault((G, ri), (req, x["id"], lab))
        return out

    def find_doors(self):
        """Door-shaped rigs (moved solid platforms of the DOOR_* shape) and
        what opens them, from the links that move the door's transforms
        traced upstream (6 hops): a lock upstream makes it that lock's gate
        (appended to ``self.gates``; the open pose is not decoded [inferred:
        it clears the doorway]); movers whose links decode make it a wired
        gate (doors on the same movers are one); an undecoded one opened by
        an actionButton or touch link is returned as an action door
        (probe-needed, class door)."""
        lv = self.lv
        locks = self.lock_map()
        lock_doors = collections.defaultdict(list)
        wired = collections.defaultdict(list)
        action = []
        for o in lv.owners:
            if o["kind"] != "platform" or o["cat"] != CAT_RIG or not o["moved"]:
                continue
            t = lv.tris_of(o["oi"])
            deck = float(lv.tri_area[t][lv.tri_nz[t] >= 0.8].sum())
            face = float(lv.tri_area[t][np.abs(lv.tri_nz[t]) < 0.3].sum())
            zr = float(np.ptp(lv.P[t][:, :, 2])) if len(t) else 0.0
            if deck >= DOOR_DECK_M2 or face < DOOR_FACE_M2 or zr < DOOR_HEIGHT_M:
                continue
            g = lv.graphs[o["G"]]
            inc = g.incoming()
            start = set()
            for a in g.ancestors(o["R"]):
                for lk, _ in inc.get(a, ()):
                    if g.plug_name(a, lk.dst_plug) in collision.TRS_PLUGS:
                        start.add(lk.src)
            seen, frontier, plugs, lock = set(), [(s_, 0) for s_ in sorted(start)], set(), None
            while frontier:
                r_, dpt = frontier.pop(0)
                if r_ in seen or dpt > 6:
                    continue
                seen.add(r_)
                if lock is None and (o["G"], r_) in locks:
                    lock = locks[(o["G"], r_)]
                for lk, _ in inc.get(r_, ()):
                    plugs.add(g.plug_name(lk.src, lk.src_plug))
                    frontier.append((lk.src, dpt + 1))
            movers = sorted({g.names[s_] for s_ in start if g.names[s_]})
            cond = F_FALSE
            for a in g.ancestors(o["R"]):
                for k, lk in self.wire.incoming(o["G"], a):
                    if g.plug_name(a, lk.dst_plug) in collision.TRS_PLUGS:
                        sg = self.wire.link(o["G"], k, lk)
                        cond = f_or(cond, None if sg.init is None else (sg.on if sg.init == 0.0 else sg.off))
            alts = self.wire.terms(cond)
            if alts:
                alts = [a for a in alts if all(p.split(":")[0] in ("arrive", "loc") or self.pad_nodes(p, "logic") for p in a[0])]
            if lock is not None:
                lock_doors[lock].append((o["oi"], movers))
            elif alts:
                wired[tuple(movers)].append((o["oi"], alts))
            elif plugs & {"actionButton", "touch"}:
                action.append({"id": f"{self.name}.door.{re.sub(r'[^A-Za-z0-9_]', '_', movers[0] if movers else o['name'])}",
                               "door": "action", "members": [o["oi"]], "member_names": [o["name"]], "movers": movers,
                               "opened_by": sorted(plugs & {"actionButton", "touch"}),
                               "records": [f"{self.name}/g{o['G']}/r{o['R']}"], "present_at_load": [True],
                               "member_state": ["door"], "requires": "true"})
        for (req, lid, lab), mem in sorted(lock_doors.items(), key=lambda kv: kv[0][1]):
            oids = [m[0] for m in mem]
            self.gates.append({"driver": sorted({x for m in mem for x in m[1]}), "members": oids,
                               "records": [f"{self.name}/g{lv.owners[oi]['G']}/r{lv.owners[oi]['R']}" for oi in oids],
                               "member_names": [lv.owners[oi]["name"] for oi in oids],
                               "member_state": ["door"] * len(oids), "present_at_load": [True] * len(oids),
                               "bound_to": [f"lock:{lid}"], "family": None, "family_class": None,
                               "id": f"{self.name}.door.{re.sub(r'[^A-Za-z0-9_]', '_', lab)}", "requires": req,
                               "door": "lock", "lock": lid})
        for movers, mem in sorted(wired.items()):
            oids = [m[0] for m in mem]
            alts = mem[0][1]
            for _, a2 in mem[1:]:
                alts = [x for x in alts if x in a2] or alts       # the leaves share their movers
            gid = f"{self.name}.door.{re.sub(r'[^A-Za-z0-9_]', '_', movers[0] if movers else lv.owners[oids[0]]['name'])}"
            while any(x["id"] == gid for x in self.gates):
                gid += "_"
            self.gates.append({"driver": list(movers), "members": oids,
                               "records": [f"{self.name}/g{lv.owners[oi]['G']}/r{lv.owners[oi]['R']}" for oi in oids],
                               "member_names": [lv.owners[oi]["name"] for oi in oids],
                               "member_state": ["door"] * len(oids), "present_at_load": [True] * len(oids),
                               "bound_to": [], "family": None, "family_class": None, "id": gid,
                               "requires": self.alts_req(alts), "alts": alts, "door": "wired", "requires_from": "wiring",
                               "pad_only": any(not items for _, items in alts)})
        seen_ids = collections.Counter()
        for d in action:
            seen_ids[d["id"]] += 1
            if seen_ids[d["id"]] > 1:
                d["id"] += f"_{seen_ids[d['id']]}"
        return action

    def gate_variant(self, g):
        """Flip the gate's members in a window around them: base regions that
        one variant region joins are separated by the gate (``merges``);
        water regions likewise (``water_merges``); its gate edges (an action
        door: probe-needed door edges) and ``destroy_from`` (regions within
        ATTACK_REACH of its barrier's shapes)."""
        lv, w = self.lv, self.W["logic"]
        col = raster(lv, np.nonzero(np.isin(lv.tri_owner, g["members"]))[0])[0]
        g["merges"], g["water_merges"], g["splits"] = [], [], []
        if not len(col):
            return
        ix, iy = col % lv.NX, col // lv.NX
        pad = 40
        x0, x1, y0, y1 = ix.min() - pad, ix.max() + pad, iy.min() - pad, iy.max() + pad
        pc = self.pairs[0]
        pix, piy = pc % lv.NX, pc // lv.NX
        win = (pix >= x0) & (pix <= x1) & (piy >= y0) & (piy <= y1)
        flip = np.isin(lv.tri_owner[self.pairs[3]], g["members"])
        vmask = np.where(flip, ~self.pmask, self.pmask) & win
        spans = Spans(lv, *(x[vmask] for x in self.pairs))
        g["_vspans"] = spans          # the flipped state in the window (map_point: what the members alone cut off)
        dmg = set(self.dmg_present)
        for oi in g["members"]:
            if lv.owners[oi]["cat"] == CAT_DAMAGE or oi in self.drag_oids:
                dmg ^= {oi}
        appear = {oi for oi, pres in zip(g["members"], g["present_at_load"]) if not pres and lv.owners[oi]["cat"] == CAT_TOGGLE} | \
            (self.crumble - set(g["members"]))
        v = Walk(lv, spans, "logic", self.water_vol, dmg, self.damage_vol,
                 Obstacles(lv, self.pairs, vmask, PROFILES["logic"]["floor_nz"]), appear)
        a, n = lookup(w.u, w.a, w.c, v.col)
        base_r = np.full(len(v.col), -1, dtype=np.int64)
        for k in range(w.mx):
            ok = (k < n) & (base_r < 0)
            j = np.where(ok, a + k, 0)
            base_r = np.where(ok & (np.abs(w.z[j] - v.z) < 0.06), w.reg[j], base_r)
        m = (v.reg >= 0) & (base_r >= 0)
        pairs = set(zip(v.reg[m].tolist(), base_r[m].tolist()))
        groups = collections.defaultdict(set)
        for a_, b_ in pairs:
            groups[a_].add(b_)
        g["merges"] = sorted(sorted(s) for s in groups.values() if len(s) > 1)
        if not all(g["present_at_load"]):
            per = collections.defaultdict(set)
            for a_, b_ in pairs:
                per[b_].add(a_)
            g["splits"] = sorted(b_ for b_, s in per.items() if len(s) > 1)
        if any(lv.owners[oi]["cat"] == CAT_DAMAGE or oi in self.drag_oids for oi in g["members"]) and self.wg.n:
            wv = WaterGrid(lv, self.water_vol, self.damage_vol, dmg, self.spans, self.swim_block_vol)
            if len(wv.col) != len(self.wg.col) or not (wv.col == self.wg.col).all():
                raise AssertionError(f"{g['id']}: the flipped water's nodes differ from the base's")
            ok = (self.wg.lab >= 0) & (wv.lab >= 0) & ~self.wg.blk     # a blocking current's split water takes no part
            grp = collections.defaultdict(set)
            for a_, b_ in zip(wv.lab[ok].tolist(), self.wg.lab[ok].tolist()):
                grp[a_].add(b_)
            g["water_merges"] = sorted(sorted(s) for s in grp.values() if len(s) > 1)
            g["water_freed_cols"] = int((self.wg.lab < 0).sum() - (wv.lab < 0).sum())
        nb = w.nreg
        for grp_ in g["merges"]:
            for a_ in grp_:
                for b_ in grp_:
                    if a_ != b_ and g.get("door") == "action":
                        self.E["logic"][(a_, b_)].append({
                            "kind": "door", "conf": "probe-needed", "ranks": [0, 0, 0, 0], "via": g["id"],
                            "why": f"open {g['member_names'][0]} ({' / '.join(g['opened_by'])} -> {', '.join(g['movers'][:2])} "
                                   "[data]); its swing is not decoded"})
                    elif a_ != b_:
                        self.E["logic"][(a_, b_)].append({"kind": "gate", "conf": "data", "ranks": [0, 0, 0, 0],
                                                          "through": [g["id"]], "why": f"walk through {g['id']} once it is open"})
        for grp_ in g.get("water_merges", []):
            for a_ in grp_:
                for b_ in grp_:
                    if a_ != b_:
                        self.E["logic"][(nb + a_, nb + b_)].append({"kind": "gate", "conf": "data", "ranks": [0, 0, 0, 0],
                                                                    "through": [g["id"]],
                                                                    "why": f"swim through {g['id']} once it is off"})
        if g.get("shapes"):
            near = set()
            rr = int(math.ceil(ATTACK_REACH / CELL))
            for sid in g["shapes"]:
                _, gs, rs = sid.split("/")
                oi = lv.by_rec.get((int(gs[1:]), int(rs[1:])))
                if oi is None:
                    continue
                c, zl, zh, _ = raster(lv, lv.tris_of(oi))[:4]
                for dx in range(-rr, rr + 1):
                    for dy in range(-rr, rr + 1):
                        if dx * dx + dy * dy > rr * rr:
                            continue
                        a, n = lookup(w.u, w.a, w.c, c + dx + dy * lv.NX)
                        for k in range(w.mx):
                            v_ = k < n
                            j = np.where(v_, a + k, 0)
                            ok = v_ & (w.reg[j] >= 0) & (w.z[j] <= zh + 1.0) & (w.z[j] >= zl - 3.0)
                            near.update(w.reg[j[ok]].tolist())
            g["destroy_from"] = sorted(near)

    def resolve_overflights(self):
        """An edge flown over a shut barrier (``over``, OverTest) names the
        gates it passes over, kept for a gate that separates walk regions and
        is not a hazard pseudo-gate, a door or opened by pads alone, when
        the edge's witness takeoff and landing lie on opposite sides of the
        barrier's plane (at least OVER_SIDE_M off it).  Such an edge is no
        free movement and barrier_cut tags it as a crossing of that gate.
        Other ``over`` marks are dropped."""
        by_drv = {tuple(g["driver"]): g for g in self.gates}
        ot, w = self.over_test, self.W["logic"]
        self.over_plane = {}
        for k, key in enumerate(ot.keys):
            g = by_drv.get(tuple(key))
            if g is not None:
                c0, nrm = ot.plane[k][:2]
                self.over_plane[g["id"]] = (c0, nrm, np.c_[ot.x[ot.g == k].ravel(), ot.y[ot.g == k].ravel()])
        n_kept, n_drop, n_same = collections.Counter(), 0, 0
        for es in self.E["logic"].values():
            for e in es:
                if not e.get("over"):
                    continue
                keep = []
                for drv in e["over"]:
                    g = by_drv.get(tuple(drv))
                    if g is None or g.get("hazard") or g.get("door") or g.get("pad_only") or \
                            not any(len(m_) > 1 for m_ in g.get("merges", ())):
                        continue
                    c0, nrm, _ = self.over_plane[g["id"]]
                    i_, j_ = e["w"]
                    sa = (w.x[i_] - c0[0]) * nrm[0] + (w.y[i_] - c0[1]) * nrm[1]
                    sb = (w.x[j_] - c0[0]) * nrm[0] + (w.y[j_] - c0[1]) * nrm[1]
                    if sa * sb >= 0 or min(abs(sa), abs(sb)) < OVER_SIDE_M:
                        n_same += 1
                        continue
                    keep.append(g["id"])
                if keep:
                    e["over"] = sorted(set(keep))
                    for gid in e["over"]:
                        n_kept[gid] += 1
                else:
                    del e["over"]
                    n_drop += 1
        self.overflight_counts = {"edges_by_gate": dict(sorted(n_kept.items())), "marks_dropped": n_drop,
                                  "gate_marks_one_side": n_same}

    def resolve_hazard_flights(self):
        """A jump or flap whose only obstacle is damage volumes that all
        belong to one gate is that gate's edge: through the gate, with the
        flight's own movement ranks (modelled)."""
        member = {oi: g["id"] for g in self.gates for oi in g["members"]}
        n = 0
        for es in self.E["logic"].values():
            for e in es:
                if e.get("haz") and not e.get("wall") and e["conf"] == "probe-needed":
                    gs = {member.get(oi) for oi in e["haz"]}
                    if len(gs) == 1 and None not in gs:
                        gid = gs.pop()
                        e["through"] = [gid]
                        e["conf"] = "modelled"
                        e["why"] = f"{e['kind']} through {gid}'s volume once it is open (otherwise it hurts)"
                        n += 1
        self.hazard_flights = n

    # ---- barrier crossings
    def confirmed_bskips(self):
        """(the level's confirmed bskip skips: id -> gate, side, kit, difficulty, confirmed; the ids not usable here)."""
        out, unused = {}, []
        cur = {h["skip"] for h in CURRENT_SKIPS.get(self.name, ())}
        for s_ in self.tricks.values():
            if s_.get("level") != self.name or "bskip" not in s_.get("tricks", ()):
                continue
            if s_.get("status") != "in_logic" or s_.get("confirmed") in (None, "no"):
                continue
            if s_["id"] in cur:
                continue            # a current's crossing (current_edges), not a barrier gate's
            req = s_.get("requires", "true")
            m = re.fullmatch(r"air>=([0-3])", req)
            side = CONFIRMED_BSKIP_SIDE.get(s_["id"])
            if side is None or not (m or req == "true") or len(s_.get("gates", [])) != 1:
                unused.append(s_["id"])
                continue
            out[s_["id"]] = {"id": s_["id"], "gate": s_["gates"][0], "side": side, "kit": int(m.group(1)) if m else 0,
                             "difficulty": s_.get("difficulty"), "confirmed": s_["confirmed"]}
        return out, unused

    def _zone_graph(self):
        """Zone -> [(zone, ranks, probe class, gates passed, needs an
        undecoded atom, edge id, a data edge)] for every logic edge between
        two zones (before any barrier tag)."""
        Z = self.zone_of
        zg = collections.defaultdict(list)
        for (a, b), es in self.E["logic"].items():
            za, zb = int(Z[a]), int(Z[b])
            if za == zb:
                continue
            for e in es:
                if min(e["ranks"]) >= 4 or e.get("skip_atom"):
                    continue
                thr = tuple(e.get("through", ())) + tuple(e.get("over", ()))   # over a gate is past it
                zg[za].append((zb, tuple(int(r) for r in e["ranks"]), probe_class(e), thr,
                               bool(e.get("needs_undecoded")) or any(t in self.undecoded for t in thr), id(e),
                               e["conf"] == "data"))
        return zg

    @staticmethod
    def _least_air(zg, starts, ti, probes, shut, excl=frozenset()):
        """Zone -> the least air level that reaches it from ``starts`` at tier
        ti with the probe classes ``probes``, the gates ``shut`` shut, every
        other gate open and the edges ``excl`` left out (a bottleneck search)."""
        best = {s_: 0 for s_ in starts}
        h = [(0, s_) for s_ in starts]
        while h:
            c, z = heapq.heappop(h)
            if c > best.get(z, 9):
                continue
            for zb, rk, pc, thr, und, eid, *_ in zg.get(z, ()):
                r = rk[ti]
                if r >= 4 or not shut.isdisjoint(thr) or eid in excl or (und and "gate-undecoded" not in probes) \
                        or (pc is not None and pc not in probes):
                    continue
                cc = max(c, r)
                if cc < best.get(zb, 9):
                    best[zb] = cc
                    heapq.heappush(h, (cc, zb))
        return best

    def _barrier_plane(self, g):
        """(centre, unit normal, XY points) of a gate's members' best-fit vertical plane, or None."""
        lv = self.lv
        tri = np.nonzero(np.isin(lv.tri_owner, g["members"]))[0]
        if not len(tri):
            return None
        GP = lv.P[tri].reshape(-1, 3)[:, :2]
        c0 = GP.mean(0)
        _, evec = np.linalg.eigh((GP - c0).T @ (GP - c0))
        return c0, evec[:, 0], GP[::max(1, len(GP) // 300)]

    def _zone_geo(self, z, zmem, geo):
        """(least XY distance from a zone's land samples to the barrier's
        members, the samples' median signed distance from its plane), 0.1 m."""
        w = self.W["logic"]
        land = [n_ for n_ in zmem[z] if n_ < w.nreg]
        idx = np.nonzero(np.isin(w.reg, land))[0] if land else np.zeros(0, np.int64)
        if not len(idx):
            return None, None
        c0, nrm, GP = geo
        P2 = np.c_[w.x[idx], w.y[idx]][::max(1, len(idx) // 2000)]
        dmin = float(np.min(np.linalg.norm(P2[:, None, :] - GP[None, :, :], axis=2)))
        return round(dmin, 1), round(float(np.median((P2 - c0) @ nrm)), 1)

    def _side_match(self, spec, d, side):
        """Does a confirmed skip's side spec (CONFIRMED_BSKIP_SIDE) name the barrier direction d (A -> B)?"""
        if spec in ("out", "in"):
            return bool(side) and spec == side
        if not isinstance(spec, dict) or "_far_z" not in d:
            return False
        near_z = {int(self.zone_of[x]) for x in d["_near"]} | {d["from"]}
        far_z = set(d["_far_z"]) | {d["to"]}
        for key, sideset in (("to_location", far_z), ("from_location", near_z), ("from_anchor", near_z)):
            if key not in spec:
                continue
            if key == "from_anchor":
                zs = {int(self.zone_of[n_]) for n_ in self.obj_at.get(spec[key], {}).get("nodes", [])}
            else:
                n_ = self.map_point("logic", self.lv.rec_points(spec[key])[0][0], gates=True)[0]
                zs = set() if n_ is None else {int(self.zone_of[n_])}
            if not zs & sideset:
                return False
        return True

    def barrier_cut(self):
        """Every connection between a gate's two sides that does not go
        through it is a skip candidate, whatever its distance from the
        barrier.  A gate's sides are the zones its open state joins.  For each
        side pair and direction A -> B, with the gate (and its parallel gates,
        those joining the same two zones) shut and every other gate open:

        - a budget is a tier, an air level and a set of probe classes (none;
          each class alone; each prefix of the ladder; bskip never).  near is
          what A freely reaches; far is every zone B reaches under some
          budget under which A does not, to a fixpoint that leaves out A's
          crossings into the current far side (else one cheap bypass makes
          every zone past it a tie) and lets a data edge (a designed way)
          count for A; zones both directions put on their far side are placed
          by the barrier's plane;
        - the crossing edges are every edge (any class but data) from what
          near reaches without entering far into far; each needs a skip:
          per (gate, A, B, kit) a held generated skip with a witness route
          from A to B, or a confirmed tricks.toml skip of the gate and
          direction when the crossing's own movement is in logic (at the
          higher of the two kits; a crossing that needs less air keeps a held
          atom beside it, so the tiers stay monotone);
        - an edge flown over a shut barrier between its two sides is a
          crossing too, of an analysed direction or of its own (geometric).

        Checked (``leaks``): from near, gate shut, no skip atom, every probe
        class, the frame-perfect tier and air 3, no far zone is reached."""
        w, E = self.W["logic"], self.E["logic"]
        nb = w.nreg
        Z = self.zone_of
        adj, fw, bw = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
        for (a, b), es in E.items():
            for e in es:
                adj[a].append((b, e))
                if free_edge(e):
                    fw[a].append(b)
                    bw[b].append(a)

        def clos(starts, g_):
            seen, st = set(starts), list(starts)
            while st:
                a_ = st.pop()
                for b_ in g_.get(a_, ()):
                    if b_ not in seen:
                        seen.add(b_)
                        st.append(b_)
            return seen

        def reach_(starts, ti, air, ok):
            seen, st = set(starts), list(starts)
            par = {s_: None for s_ in starts}
            while st:
                a_ = st.pop()
                for b_, e in adj.get(a_, ()):
                    if b_ in seen or e["ranks"][ti] > air or not ok(a_, b_, e):
                        continue
                    seen.add(b_)
                    par[b_] = (a_, e)
                    st.append(b_)
            return seen, par

        zmem = collections.defaultdict(list)
        for n_ in range(len(Z)):
            zmem[int(Z[n_])].append(n_)
        spawn_z = {int(Z[n_]) for n_ in self.spawn["logic"]}
        spawn_free = {int(Z[n_]) for n_ in clos(self.spawn["logic"], fw)}
        confirmed, self.confirmed_ignored = self.confirmed_bskips()
        self.confirmed_bskip = confirmed
        zg = self._zone_graph()
        classes = {x[2] for v in zg.values() for x in v if x[2]} - {"bskip", SKIP_CLASS}
        if any(x[4] for v in zg.values() for x in v):
            classes.add("gate-undecoded")
        classes = sorted(classes)
        lad = [p for p in PROBE_LADDER if p != "bskip" and p in classes]
        budgets = list(dict.fromkeys(tuple(sorted(p)) for p in
                                     [()] + [(c,) for c in classes] + [tuple(lad[:k]) for k in range(1, len(lad) + 1)]))
        dirs, tags = [], collections.defaultdict(list)
        # undecoded gates and gates that never open are analysed too; hazard pseudo-gates and pad-only gates stay out
        gpairs = {}
        for g in self.gates:
            if g.get("hazard") or g.get("pad_only"):
                continue
            groups = list(g.get("merges", [])) + [[nb + r for r in grp] for grp in g.get("water_merges", [])]
            gpairs[g["id"]] = sorted({tuple(sorted({int(Z[r]) for r in grp})) for grp in groups
                                      if len({int(Z[r]) for r in grp}) > 1})
        par = collections.defaultdict(set)
        for gid_, ps in gpairs.items():
            for zs in ps:
                for za_ in zs:
                    for zb_ in zs:
                        if za_ < zb_:
                            par[(za_, zb_)].add(gid_)

        def finish(d, g, za, zb, near, near_z, side, far_z, reached_a, reached_b, back_z, notg):
            """The ties, the crossing edges and the confirmed skips of a direction whose far side is final."""
            gid = d["gate"]
            d["_ties"] = (reached_a & reached_b) - far_z - back_z - near_z
            geo = self._barrier_plane(g)
            if geo is not None and d["_ties"]:
                sa, sb = self._zone_geo(za, zmem, geo)[1], self._zone_geo(zb, zmem, geo)[1]
                sg = 1.0 if (sb if sb is not None else 0.0) >= (sa if sa is not None else 0.0) else -1.0
                d["_tie_geo"] = {z: (lambda t_: (t_[0], None if t_[1] is None else t_[1] * sg))(
                    self._zone_geo(z, zmem, geo)) for z in d["_ties"]}
            far = {n_ for z in far_z for n_ in zmem[z]}
            src, st = set(near), list(near)
            while st:
                a_ = st.pop()
                for b_, e in adj.get(a_, ()):
                    if b_ in src or b_ in far or not notg(a_, b_, e):
                        continue
                    src.add(b_)
                    st.append(b_)
            src |= {n_ for z in d.get("_geo_near", ()) for n_ in zmem[z]}
            cut = [(a_, b_, e) for a_ in src for b_, e in adj.get(a_, ()) if b_ in far and notg(a_, b_, e)]
            d["_far"], d["_near"] = far, near
            d["_src_z"] = {int(Z[n_]) for n_ in src}
            d["data_edges"] = sum(1 for c in cut if c[2]["conf"] == "data")
            d["_cut"] = [c for c in cut if c[2]["conf"] != "data"]
            m = [s_ for s_ in confirmed.values() if s_["gate"] == gid and self._side_match(s_["side"], d, side)]
            d["confirmed"] = sorted(m, key=lambda s_: (s_["kit"], s_["difficulty"] or 9, s_["id"]))
            for a_, b_, e in d["_cut"]:
                tags[id(e)].append(d)

        gsides, tree = {}, []

        def sample_index():
            if not tree:
                tree.append(RadiusIndex(np.c_[w.x, w.y], GEO_SIDE_R))
            return tree[0]

        def zone_sides(gid):
            """Zone -> the side (+1 / -1) of the gate's plane its land samples within GEO_SIDE_R of the members lie on,
            by their median, when it is at least OVER_SIDE_M off the plane."""
            if gid not in gsides:
                out = {}
                pl = self.over_plane.get(gid)
                if pl is not None:
                    c0, nrm, GP = pl
                    GP = GP[::max(1, len(GP) // 300)]
                    js = np.unique(sample_index().pairs(GP)[1])
                    js = js[w.reg[js] >= 0] if len(js) else js
                    if len(js):
                        zz = Z[w.reg[js]]
                        sd = (w.x[js] - c0[0]) * nrm[0] + (w.y[js] - c0[1]) * nrm[1]
                        for z_ in np.unique(zz).tolist():
                            med = float(np.median(sd[zz == z_]))
                            if abs(med) >= OVER_SIDE_M:
                                out[int(z_)] = 1 if med > 0 else -1
                gsides[gid] = out
            return gsides[gid]

        for g in self.gates:
            gid = g["id"]
            if gid not in gpairs:
                continue
            for zs in gpairs[gid]:
                todo = []
                for za in zs:
                    for zb in zs:
                        if za == zb:
                            continue
                        shut = frozenset(par[(min(za, zb), max(za, zb))]) | {gid}
                        notg = lambda a_, b_, e, shut=shut: shut.isdisjoint(e.get("through", ())) and \
                            shut.isdisjoint(e.get("over", ()))      # noqa: E731
                        A, B = zmem[za], zmem[zb]
                        fa = clos(A, fw)
                        side = "out" if za in spawn_z or (za in spawn_free and zb not in spawn_free) else \
                            "in" if zb in spawn_z or (zb in spawn_free and za not in spawn_free) else None
                        d = {"gate": gid, "from": za, "to": zb, "side": side, "_shut": shut,
                             **({"shut_with": sorted(shut - {gid})} if len(shut) > 1 else {})}
                        dirs.append(d)
                        d["bypass_default"], d["bypass_any"] = {}, {}
                        for key, P in (("bypass_default", ()), ("bypass_any", budgets[-1])):
                            for ti, tn in enumerate(TIERS):
                                m = self._least_air(zg, [za], ti, P, shut).get(zb, 9)
                                if m < 4:
                                    d[key][tn] = m
                        if set(B) & fa:
                            d["not_separated"] = True
                            continue
                        near = fa
                        near_z = {int(Z[n_]) for n_ in near}
                        far_z = {int(Z[n_]) for n_ in clos(B, fw) | clos(B, bw)} - near_z
                        d["far_rounds"] = 0
                        prev_z = None
                        while True:
                            d["far_rounds"] += 1
                            src_z, st = set(near_z), list(near_z)
                            while st:
                                a_ = st.pop()
                                for x_ in zg.get(a_, ()):
                                    if x_[0] not in src_z and x_[0] not in far_z and shut.isdisjoint(x_[3]):
                                        src_z.add(x_[0])
                                        st.append(x_[0])
                            excl = {x_[5] for a_ in src_z for x_ in zg.get(a_, ()) if x_[0] in far_z and shut.isdisjoint(x_[3])
                                    and not x_[6]}
                            new_z, back_z, reached_a, reached_b = set(), set(), set(), set()
                            for ti in range(4):
                                for P in budgets:
                                    mA = self._least_air(zg, [za], ti, P, shut, excl)
                                    mB = self._least_air(zg, [zb], ti, P, shut, excl)
                                    reached_a |= set(mA)
                                    reached_b |= set(mB)
                                    new_z |= {z for z, c in mB.items() if c < mA.get(z, 9)}
                                    back_z |= {z for z, c in mA.items() if c < mB.get(z, 9)}
                            new_z |= far_z - (reached_a - new_z)
                            new_z -= near_z
                            if new_z == far_z or new_z == prev_z or d["far_rounds"] >= 12:
                                far_z = new_z | far_z if new_z != far_z else new_z
                                break
                            prev_z, far_z = far_z, new_z
                        d["_far_z"] = far_z
                        if zb not in far_z:
                            d["not_separated"] = "a designed way (a data edge) joins the sides"
                            continue
                        todo.append((d, g, za, zb, near, near_z, side, far_z, reached_a, reached_b, back_z, notg))
                byd = {(t_[0]["from"], t_[0]["to"]): t_[0] for t_ in todo}
                zsd = zone_sides(gid) if len(byd) > 1 else {}
                for (fa_, fb_), d1 in sorted(byd.items()):
                    d2 = byd.get((fb_, fa_))
                    if d2 is None or fa_ > fb_:
                        continue
                    sA, sB = zsd.get(fa_), zsd.get(fb_)
                    if sA is not None and sB is not None and sA != sB:
                        for z in sorted(d1["_far_z"] & d2["_far_z"]):
                            sz = zsd.get(z)
                            dd = d1 if sz == sA else d2 if sz == sB else None
                            if dd is not None and z != dd["to"]:
                                dd["_far_z"].discard(z)
                                dd.setdefault("_geo_near", set()).add(z)
                for item in todo:
                    finish(*item)
        # an edge flown over a shut barrier between the gate's two sides is a crossing of that gate: of an analysed
        # direction, or of a direction of its own (geometric) placed by the barrier's plane or the edge's own zones
        by_gate = collections.defaultdict(list)
        for d in dirs:
            if "_src_z" in d:
                by_gate[d["gate"]].append(d)
        sides = {}

        def gate_sides(gid):
            if gid not in sides:
                geo = self.over_plane.get(gid)
                out = []
                if geo is not None:
                    c0, nrm, GP = geo
                    idx = RadiusIndex(GP, OVER_SIDE_R)
                    for grp in self.gate_by_id[gid].get("merges", ()):
                        sg = {}
                        for r_ in grp:
                            js = np.nonzero(w.reg == r_)[0]
                            if not len(js):
                                continue
                            P2 = np.c_[w.x[js], w.y[js]]
                            P2 = P2[np.unique(idx.pairs(P2)[0])]
                            if len(P2):
                                sg[r_] = float(np.median((P2 - c0) @ nrm))
                        out.append(sg)
                sides[gid] = (geo, out)
            return sides[gid]

        geo_d = {}
        self.over_same_side = 0
        for (a_, b_), es in E.items():
            za_, zb_ = int(Z[a_]), int(Z[b_])
            if za_ == zb_:
                continue
            for e in es:
                for gid in e.get("over", ()):
                    if any(d_["gate"] == gid for d_ in tags.get(id(e), ())):
                        continue
                    d = next((d_ for d_ in by_gate.get(gid, ()) if za_ in d_["_src_z"] and zb_ in d_["_far_z"]), None)
                    if d is None:
                        geo, sg_list = gate_sides(gid)
                        pair = None
                        if geo is not None:
                            c0, nrm, _ = geo
                            i_, j_ = e["w"]
                            sa = float((np.array([w.x[i_], w.y[i_]]) - c0) @ nrm)
                            sb = float((np.array([w.x[j_], w.y[j_]]) - c0) @ nrm)
                            known = {(d_["from"], d_["to"]) for d_ in by_gate.get(gid, ())}
                            cands = []
                            for sg in sg_list:
                                ra = sorted({int(Z[r_]) for r_, v_ in sg.items() if v_ * sa > 0})
                                rb = sorted({int(Z[r_]) for r_, v_ in sg.items() if v_ * sb > 0})
                                cands += [(x_, y_) for x_ in ra for y_ in rb if x_ != y_]
                            pair = next((c_ for c_ in cands if c_ in known), cands[0] if cands else None)
                        if pair is None:
                            if not gpairs.get(gid) and not any(len({int(Z[r_]) for r_ in grp}) > 1
                                                             for grp in self.gate_by_id[gid].get("merges", ())):
                                continue    # its sides lie in one zone: a flight over it is plain
                            self.over_same_side += 1
                            pair = (za_, zb_)
                        d = next((d_ for d_ in by_gate.get(gid, ()) if (d_["from"], d_["to"]) == pair), None)
                        if d is None:
                            d = geo_d.get((gid,) + pair)
                            if d is None:
                                d = geo_d[(gid,) + pair] = {
                                    "gate": gid, "from": pair[0], "to": pair[1], "side": None, "geometric": True,
                                    "bypass_default": {}, "bypass_any": {}, "_cut": [], "_near": set(zmem[pair[0]]),
                                    "_far": set(zmem[pair[1]]), "_far_z": {pair[1]}, "_shut": frozenset([gid])}
                                m = [s_ for s_ in confirmed.values()
                                     if s_["gate"] == gid and self._side_match(s_["side"], d, None)]
                                d["confirmed"] = sorted(m, key=lambda s_: (s_["kit"], s_["difficulty"] or 9, s_["id"]))
                                dirs.append(d)
                    d["_cut"].append((a_, b_, e))
                    tags[id(e)].append(d)
        self.over_dirs = len(geo_d)

        def cover(e):
            """The confirmed skips that cover crossing e (one list per way, each the skips it takes together) and
            their least kit; ([], None) when a direction e crosses has none or e's own movement is not in logic."""
            ds = tags.get(id(e), ())
            if not ds or not all(d_["confirmed"] for d_ in ds) or e["conf"] not in CONFIRMABLE:
                return [], None
            combos = [[S] for S in ds[0]["confirmed"]] if len(ds) == 1 else [[d_["confirmed"][0] for d_ in ds]]
            return combos, min(max(S["kit"] for S in c_) for c_ in combos)

        gen = {}
        for d in dirs:
            for a_, b_, e in d.get("_cut", ()):
                kmin = cover(e)[1]
                for ti, r in enumerate(e["ranks"]):
                    r = int(r)
                    if r >= 4 or (kmin is not None and r >= kmin):
                        continue
                    k = (d["gate"], d["from"], d["to"], r)
                    x = gen.setdefault(k, {"dir": d, "kit": r, "difficulty": TIER_N[TIERS[ti]], "crossings": set()})
                    x["difficulty"] = min(x["difficulty"], TIER_N[TIERS[ti]])
                    x["crossings"].add((int(Z[a_]), int(Z[b_])))
        # witness routes (before any tag): from A to one of the skip's crossings and on to B (or to the crossing's
        # landing), at the least tier and air, without probe-needed edges when possible
        for k, x in sorted(gen.items(), key=lambda kv: kv[0]):
            d, K = x["dir"], x["kit"]
            gid = d["gate"]
            mine = [(a_, b_, e) for a_, b_, e in d["_cut"]
                    if any(int(r) == K and not (cover(e)[1] is not None and int(r) >= cover(e)[1]) for r in e["ranks"])]
            found = None
            for probes in (False, True):
                for ti in range(x["difficulty"] - 1, 4):
                    cross = {(a_, b_): e for a_, b_, e in mine if int(e["ranks"][ti]) <= K
                             and (probes or e["conf"] != "probe-needed")}
                    for air in range(K, 4):
                        ok1 = lambda a_, b_, e, gid=gid, probes=probes: gid not in e.get("through", ()) \
                            and gid not in e.get("over", ()) and b_ not in d["_far"] and (probes or e["conf"] != "probe-needed")  # noqa: E731
                        s1, p1 = reach_(zmem[d["from"]], ti, air, ok1)
                        starts = sorted({b_ for (a_, b_) in cross if a_ in s1})
                        if not starts:
                            continue
                        ok2 = lambda a_, b_, e, gid=gid, probes=probes: gid not in e.get("through", ()) \
                            and gid not in e.get("over", ()) and (probes or e["conf"] != "probe-needed")      # noqa: E731
                        s2, p2 = reach_(starts, ti, air, ok2)
                        hit = sorted(set(zmem[d["to"]]) & s2)
                        found = (ti, air, s1, p1, p2, hit[0] if hit else starts[0], cross, bool(hit), probes)
                        break
                    if found:
                        break
                if found:
                    break
            if not found:
                x["route"] = None
                continue
            ti, air, s1, p1, p2, end, cross, to_b, probes = found
            x["route_tier"], x["route_reaches_side"], x["crossing_difficulty"] = TIERS[ti], to_b, x["difficulty"]
            x["difficulty"] = max(x["difficulty"], TIER_N[TIERS[ti]])
            path2, n_ = [], end
            while p2.get(n_) is not None:
                path2.append(n_)
                n_ = p2[n_][0]
            v0 = n_
            u0 = next(a_ for (a_, b_) in sorted(cross) if b_ == v0 and a_ in s1)
            path1, n_ = [u0], u0
            while p1.get(n_) is not None:
                n_ = p1[n_][0]
                path1.append(n_)
            zp = [int(Z[n_]) for n_ in list(reversed(path1)) + [v0] + list(reversed(path2))]
            x["route"] = [z_ for i_, z_ in enumerate(zp) if i_ == 0 or zp[i_ - 1] != z_]
            x["route_requires"] = RANK_REQ[air]
            x["route_uses_probe_edges"] = probes
            x["crossing_used"] = (int(Z[u0]), int(Z[v0]))
            x["crossing_movement"] = dict(sorted(collections.Counter(
                f"{e['kind']} ({e['conf']}{', ' + probe_class(e) if probe_class(e) else ''})" for _, _, e in mine).items()))
        # tag the crossings: per tier the confirmed atom when every direction the edge crosses has a confirmed skip
        # (at the higher of the crossing's kit and the skip's), and the held generated atom where the crossing needs
        # less air than the skip or no confirmed skip covers it
        new_edges = []
        for (a_, b_), es in E.items():
            for e in list(es):
                ds = tags.get(id(e))
                if not ds:
                    continue
                combos, kit_min = cover(e)
                if e.get("over") and {d_["gate"] for d_ in ds} <= set(e["over"]):
                    # with the gate open its member is gone: the same flight is the gate's own edge
                    tc = {k_: v_ for k_, v_ in e.items() if k_ != "over"}
                    tc["through"] = sorted(set(e.get("through", ())) | set(e["over"]))
                    tc["why"] = f"{e['kind']} over the place of {' & '.join(e['over'])} once it is open ({e.get('why') or e['conf']})"
                    new_edges.append(((a_, b_), tc))
                held_r = [int(r) if int(r) < 4 and (kit_min is None or int(r) < kit_min) else 4 for r in e["ranks"]]
                base = {"conf_movement": e["conf"], "trick": "bskip",
                        "why": f"{e['kind']} into the far side of {' & '.join(sorted({d_['gate'] for d_ in ds}))} while it is "
                               f"shut (a barrier bypass; {e.get('why') or e['conf']})"}
                for c_ in combos:
                    kit = max(S["kit"] for S in c_)
                    skip_r = [max(int(r), kit) if int(r) < 4 else 4 for r in e["ranks"]]
                    info = sorted({(d_["gate"], d_["from"], d_["to"], S["id"]) for d_, S in zip(ds, c_)})
                    new_edges.append(((a_, b_), dict(e, **base, bskip=info, ranks=skip_r, conf="skip", skip_atom=True)))
                if any(r < 4 for r in held_r):
                    e.update(base, bskip=sorted({(d_["gate"], d_["from"], d_["to"], None) for d_ in ds}), ranks=held_r,
                             conf="probe-needed")
                else:
                    es.remove(e)
        for k_, e2 in new_edges:
            E[k_].append(e2)
        for d in dirs:
            for S in (d.get("confirmed") or ()) if not d.get("not_separated") else ():
                E[(zmem[d["from"]][0], zmem[d["to"]][0])].append({
                    "kind": "skip", "conf": "skip", "skip_atom": True, "ranks": [S["kit"]] * 4,
                    "bskip": [(d["gate"], d["from"], d["to"], S["id"])], "trick": "bskip",
                    "why": f"the confirmed skip {S['id']} ({S['confirmed']}): past {d['gate']} while it is shut"})
        adj.clear()
        for (a_, b_), es in E.items():
            for e in es:
                adj[a_].append((b_, e))
        for d in dirs:
            if d.get("not_separated") or "_cut" not in d or d.get("geometric"):
                continue
            ok = lambda a_, b_, e, shut=d["_shut"]: shut.isdisjoint(e.get("through", ())) and e.get("trick") != "bskip"  # noqa: E731
            d["leaks"] = bool(d["_far"] & reach_(d["_near"], 3, 3, ok)[0])
            if d["leaks"]:      # a way past the shut gate the side analysis missed (e6's AcidBlock_02, Step R1.11c)
                d["not_separated"] = "a way past the shut gate joins the sides (every probe class)"
        self.bskip_dirs, self.bskip_gen, self.bskip_budgets = dirs, gen, budgets
        used_c = {S["id"] for d in dirs for S in d.get("confirmed") or ()}
        self.confirmed_unmatched = {k: f"no direction of {v['gate']} matches its side {v['side']} (CONFIRMED_BSKIP_SIDE)"
                                    for k, v in confirmed.items() if k not in used_c}

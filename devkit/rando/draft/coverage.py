"""Reach's locations and coverage: where each pickup is reached from, and
how much of the level each rung of items, skips, gates and probes reaches.

Part of the reach model (Step R1.3c; reach v6's ``locations`` and
``coverage``), mixed into :class:`~.reach.Reach`:

* :meth:`Coverage.locations`: location -> node for every pool pickup
  (all its gen points), in the node's own air gap and with a wall-free
  straight segment from the floor sample; a pickup whose floor stands in
  a damage volume is ``in-hazard``.  A pickup cut off from its floor by
  one gate's members alone, or enclosed by a gate member, needs that
  gate; its generated ``gated_by`` (§5.6) likewise.
* :meth:`Coverage.coverage`: per tier, the ladder of rungs (nothing, air
  powers, the confirmed skips, gates open, then each probe class), the
  least air per location (gates shut and open), the least flap flights,
  the side rows, R_phys, and the exits' least air.

Every reach here is a fixpoint over the events: a pad, a pickup or an
arrival is set once its nodes are reached (:meth:`Coverage.bfs`).
Authoring only (numpy); coordinates stay in memory.
"""

from __future__ import annotations

import collections

import numpy as np

from azurkit.tools.randomizer.draft.floors import DERIVED, PROFILES
from devkit.rando.draft.gates import PICK_STAND, PROBE_LADDER, SKIP_CLASS
from azurkit.tools.randomizer.draft.wiring import TIERS


class Coverage:
    """The location and coverage methods of :class:`~.reach.Reach`."""

    def gated_by_atoms(self, loc):
        """Each generated id in a location's ``gated_by`` as its atom (§5.6): a
        keylord -> its event, an obsidian lock -> its hand button, a geode ->
        its generated requires, a boss -> its event; else None."""
        gen = self.gen
        hand = {b.get("of"): b["id"] for b in self.toml.get("button", [])}
        kl = {k["id"]: k for k in gen.get("keylords", [])}
        ol = {o["id"] for o in gen.get("obsidian_locks", [])}
        geo = {x["id"]: x for x in gen.get("geodes", [])}
        boss = {x["id"]: x for x in gen.get("bosses", [])}
        out = []
        for gid in loc.get("gated_by") or []:
            if gid in kl and kl[gid].get("event"):
                out.append({"id": gid, "atom": f"event:{kl[gid]['event']}"})
            elif gid in ol:
                out.append({"id": gid, "atom": f"button:{hand[gid]}" if gid in hand else None})
            elif gid in geo and geo[gid].get("requires"):
                out.append({"id": gid, "atom": geo[gid]["requires"]})
            elif gid in boss and boss[gid].get("event"):
                out.append({"id": gid, "atom": f"event:{boss[gid]['event']}"})
            else:
                out.append({"id": gid, "atom": None})
        return out

    def locations(self):
        lv, env = self.lv, self.env
        greq = {g["id"]: g["requires"] for g in self.gates + self.doors}
        self.loc = {}
        for loc in self.gen.get("locations", []):
            if not loc["pool"] or not loc["id"].startswith(self.name + "/"):
                continue
            pts, ap = lv.rec_points(loc["id"])
            ent = {"id": loc["id"], "class": loc["class"], "item": loc["item"], "points": len(pts), "approx": ap}
            for prof in DERIVED:
                if prof == "logic":
                    maps = [self.map_point(prof, p, gates=True) for p in pts[:50]]
                    r, how, dz, thr = maps[0]
                else:
                    maps = [self.map_point(prof, p) for p in pts[:50]]
                    (r, how, dz), thr = maps[0], []
                ent[prof] = {"node": r, "how": how, "dz": None if dz is None else round(dz, 1)}
                if thr:
                    ent[prof]["through"] = thr
                if how == "jump":
                    if prof == "logic":
                        rk = [int(env.rise_rank(t, np.array([dz - PICK_STAND]))[0]) for t in PROFILES[prof]["tiers"]]
                    else:
                        rk = [int(env.rise_rank("phys", np.array([dz - PICK_STAND]))[0])] * 4
                    ent[prof]["ranks"] = np.minimum.accumulate(rk).tolist()     # the tiers are monotone
                elif how in ("floor", "swim", "slide"):
                    ent[prof]["ranks"] = [0, 0, 0, 0]
                else:
                    ent[prof]["ranks"] = [4, 4, 4, 4]
                spread = sorted({m[0] for m in maps if m[0] is not None})
                if len(spread) > 1:
                    ent[prof]["points_span_nodes"] = len(spread)
            if ent["logic"]["node"] is None or ent["logic"]["how"] == "air":
                sup = self.support(pts[0])
                if sup:
                    ent["support"] = sup
            if ent["logic"]["how"] == "in-hazard":
                dz_, oi_ = self.hazard_floor("logic", pts[0])
                ent["in_hazard"] = {"volume": lv.owners[oi_]["name"], "dz": round(dz_, 1),
                                    "gate": next((g["id"] for g in self.gates if oi_ in g["members"]), None)}
            encl = self.enclosed_by(pts[0])
            if encl:
                ent["enclosed_by"] = encl
            data = self.gated_by_atoms(loc)
            if data:
                ent["gated_by"] = data
            cut = set(ent["logic"].get("through", [])) | set(encl)
            action = {d["id"] for d in self.doors}
            gates = sorted(cut - action)
            ent["gates"] = gates
            ent["doors"] = sorted(cut & action)          # an action door: probe-needed (class door), no requirement
            atoms = [greq.get(g) for g in gates] + [d["atom"] for d in data]
            ent["gate_atoms"] = sorted({a for a in atoms if a})
            ent["gate_undecoded"] = sorted({g for g in gates if greq.get(g) is None} |
                                           {d["id"] for d in data if d["atom"] is None})
            ent["gate_need"] = bool(gates or data)
            self.loc[loc["id"]] = ent

    def loc_ok(self, lid, seen, ti, air, gopen, probes=(), fl=None):
        """Is location lid reached at tier ti with air level <= air, given the
        nodes ``seen``, gates open or not, and the probe classes allowed?  A
        gated location needs its gates passable and its data atoms (gates
        open), an undecoded gate the gate-undecoded class too; an item high
        above any floor counts only on its own ``float`` rung."""
        loc = self.loc[lid]
        m = loc["logic"]
        if m["node"] is None or m["node"] not in seen:
            return False
        if fl is None:
            fl = self._bfs_flags      # the flags the bfs that gave `seen` set
        if m["how"] == "air":
            if "float" not in probes:
                return False
        elif m["ranks"][ti] > air:
            return False
        if loc.get("gate_need"):
            for g_ in loc.get("gates", ()):
                if not self.gate_ok(g_, gopen, fl, probes, air=air):
                    return False
            if not self.items_ok([d_["atom"] for d_ in loc.get("gated_by", ()) if d_["atom"]], gopen, air):
                return False
            if loc.get("gate_undecoded") and "gate-undecoded" not in probes:
                return False
        if loc.get("doors") and "door" not in probes:
            return False
        return True

    def flags_set(self, prof, seen, ti, air, probes, gopen, fl):
        out = set()
        for at, f in self.flagdef.items():
            if f["kind"] == "loc":
                if f["loc"] in getattr(self, "loc", {}) and self.loc_ok(f["loc"], seen, ti, air, gopen, probes, fl):
                    out.add(at)
            elif f["kind"] == "arrive":
                if f["spawn"]:
                    out.add(at)
            elif f["nodes"][prof] & seen:
                out.add(at)
        return out

    def bfs(self, prof, ti, air, allow_probe, gates_open, starts, no_slip=False, only_gate=None):
        """Nodes reached from ``starts`` at tier ti with air level <= air (gate
        edges with the gates open, the probe classes allow_probe), to a
        fixpoint over the flags its nodes set; R_phys ignores flags."""
        adj = self._adjc.get(prof)
        if adj is None:
            adj = self._adjc[prof] = self._adj(prof)
        fl = None if prof == "phys" else set()
        while True:
            seen = set(starts)
            stack = list(starts)
            while stack:
                a = stack.pop()
                for b, e in adj.get(a, ()):
                    if b in seen or not self.usable(e, ti, air, allow_probe, gates_open, only_gate, no_slip, fl):
                        continue
                    seen.add(b)
                    stack.append(b)
            if fl is None:
                self._bfs_flags = None
                return seen
            new = self.flags_set(prof, seen, ti, air, allow_probe, gates_open, fl) - fl
            if not new:
                self._bfs_flags = fl
                return seen
            fl |= new

    def flap_counts(self, ti, air=3):
        """Node -> the least flap flights on a path from the spawn at tier ti
        (0-1 BFS; gates shut, no probe-needed edge, the flags reach sets)."""
        adj = self._adj("logic")
        self.bfs("logic", ti, air, (), False, self.spawn["logic"])
        fl = set(self._bfs_flags)
        dist = {s_: 0 for s_ in self.spawn["logic"]}
        dq = collections.deque(self.spawn["logic"])
        while dq:
            a = dq.popleft()
            da = dist[a]
            for b, e in adj.get(a, ()):
                if not self.usable(e, ti, air, (), False, fl=fl):
                    continue
                wgt = 1 if e["kind"] == "flap" else 0
                if dist.get(b, 10 ** 9) > da + wgt:
                    dist[b] = da + wgt
                    (dq.append if wgt else dq.appendleft)(b)
        return dist

    def coverage(self):
        first, arrivals = self.spawn_ids
        cov = {"spawn": first, "arrival_spots": arrivals, "tiers": {}}
        locs = sorted(self.loc)
        first_reach = {}
        for ti, tname in enumerate(TIERS):
            steps = [("nothing", 0, (), False), ("air powers", 3, (), False),
                     ("air powers + confirmed skips", 3, (SKIP_CLASS,), False), ("gates open", 3, (SKIP_CLASS,), True)]
            acc = [SKIP_CLASS]
            for pc in PROBE_LADDER:
                acc = acc + [pc]
                steps.append((f"+probe:{pc}", 3, tuple(acc), True))
            res, fr = [], {}
            for label, air, probes, gopen in steps:
                seen = self.bfs("logic", ti, air, probes, gopen, self.spawn["logic"])
                got = [lid for lid in locs if self.loc_ok(lid, seen, ti, air, gopen, probes)]
                for lid in got:
                    fr.setdefault(lid, label)
                res.append({"state": label, "items": len(got), "of": len(locs),
                            "pct": round(100.0 * len(got) / max(len(locs), 1), 1),
                            "by_class": dict(sorted(collections.Counter(self.loc[x]["class"] for x in got).items())),
                            "zones_reached": len({int(self.zone_of[n]) for n in seen})})
            cov["tiers"][tname] = res
            first_reach[tname] = fr
        # the least air level that reaches each location from the spawn (no probe-needed edge), gates shut and open
        self.min_air = {lid: {} for lid in locs}
        self.min_air_open = {lid: {} for lid in locs}
        for ti, tname in enumerate(TIERS):
            for gopen, store in ((False, self.min_air), (True, self.min_air_open)):
                for air in (3, 2, 1, 0):
                    seen = self.bfs("logic", ti, air, (), gopen, self.spawn["logic"])
                    for lid in locs:
                        if self.loc[lid]["logic"]["how"] != "air" and self.loc_ok(lid, seen, ti, air, gopen):
                            store[lid][tname] = air
        # the flap budget: every flap edge assumes a full gauge, which does not refill on landing; per location the
        # least flap flights from the spawn, and side rows for at most 0 and 1 flap flights
        self.flaps_min = {lid: {} for lid in locs}
        flap_rows = {}
        for ti, tname in enumerate(TIERS):
            dist = self.flap_counts(ti)
            for lid in locs:
                if self.loc[lid]["logic"]["how"] != "air" and self.loc_ok(lid, dist, ti, 3, False):
                    self.flaps_min[lid][tname] = dist[self.loc[lid]["logic"]["node"]]
            flap_rows[tname] = [{"state": f"air powers, at most {k} flap flight{'s' if k != 1 else ''} on the way",
                                 "items": sum(1 for lid in locs if self.flaps_min[lid].get(tname, 99) <= k)}
                                for k in (0, 1)]
        # side rows (not cumulative): no item but every probe-needed edge; and per probe class
        for ti, tname in enumerate(TIERS):
            for label, probes in [("nothing + confirmed skips + all probe-needed edges", (SKIP_CLASS,) + PROBE_LADDER)] + \
                    [(f"nothing + probe:{pc} only", (pc,)) for pc in (SKIP_CLASS,) + PROBE_LADDER]:
                seen = self.bfs("logic", ti, 0, probes, False, self.spawn["logic"])
                got = [lid for lid in locs if self.loc_ok(lid, seen, ti, 0, False, probes)]
                cov.setdefault("side", {}).setdefault(tname, []).append({"state": label, "items": len(got)})
            seen = self.bfs("logic", ti, 0, (), False, self.spawn["logic"], no_slip=True)
            got = [lid for lid in locs if self.loc_ok(lid, seen, ti, 0, False)]
            cov["side"][tname].append({"state": "nothing, near-flat slippery floors NOT used", "items": len(got)})
            cov["side"][tname] += flap_rows[tname]
        # R_phys
        seen = self.bfs("phys", 0, 3, PROBE_LADDER, True, self.spawn["phys"])
        got = [lid for lid in locs if self.loc[lid]["phys"]["node"] in seen]
        cov["phys"] = {"state": "R_phys (rig floors at rest pose, slippery, steep, phys envelope, all probes, gates open)",
                       "items": len(got), "of": len(locs), "pct": round(100.0 * len(got) / max(len(locs), 1), 1)}
        for lid in got:
            for tname in TIERS:
                first_reach[tname].setdefault(lid, "R_phys only")
        why = collections.Counter()
        for lid in locs:
            fr = first_reach["safe"].get(lid)
            if fr is None:
                fr = {"unplaced": "unplaced (no floor or water within 2 cells)", "kill-field": "inside a kill field",
                      "in-hazard": "its floor stands in a damage volume (removed from the logic walk)",
                      "walled": "a solid cuts it off from every floor within 2 cells, and no single gate opens it",
                      "air": "high above any floor (spring, updraft or a ledge above)"}.get(self.loc[lid]["logic"]["how"],
                                                                                            "no path found")
            why[fr] += 1
        cov["first_state_safe"] = dict(sorted(why.items()))
        # the exits' least air per tier: default logic, the gates open, and the confirmed skips
        ex = {x["id"]: {"name": x["name"], "dest_level": x["dest_level"]} for x in self.gen.get("exits", [])
              if self.obj_at.get(x["id"], {}).get("nodes")}
        for key, probes, gopen in (("least_air", (), False), ("least_air_gates_open", (), True),
                                   ("least_air_confirmed_skips", (SKIP_CLASS,), False)):
            for ti, tname in enumerate(TIERS):
                for air in (3, 2, 1, 0):
                    seen = self.bfs("logic", ti, air, probes, gopen, self.spawn["logic"])
                    for gid, x in ex.items():
                        x.setdefault(key, {t: None for t in TIERS})
                        if seen & set(self.obj_at[gid]["nodes"]):
                            x[key][tname] = air
        cov["exits"] = ex
        st = [n_ for sid in arrivals for n_ in self.obj_at.get(sid, {}).get("nodes", [])]
        if st:
            seen = self.bfs("logic", 0, 0, (), False, st)
            cov["from_any_arrival_safe_nothing"] = sum(1 for lid in locs if self.loc_ok(lid, seen, 0, 0, False))
        self.cov, self.first_reach = cov, first_reach

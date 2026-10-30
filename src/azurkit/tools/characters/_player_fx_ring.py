"""X38's table: each worn body's ranged-attack effects as the ring plays
them (Step 2.149; D429, D430; ``player_model/fx_ring.c``).

A swing whose clip turns an emitter of the body's ``fx/fx_default`` on
(a switch: a bound transform whose translate drives the emitter's
``enable`` or ``emitRate`` through a link) or carries one far from the
body (a marker the clip moves 2 model units or more from its rest) gets
its own copy of that graph, spawned bound at the attack's entry; the
next clip change detaches it, and its emitters run on, frozen where
they were, to the end of their window in the clip (its *off*), or, on
the body's rig (a bone, the critter, or a marker its idle clip keys: a
waist, a mouth, a jaw), 0.33 s after the detach (:data:`RIG_CLOSE`);
then each fades over :data:`RAMP_S`, its close attribute (one no link
writes) goes to 0 (a window that closes through its system writes only
the rate: the system's enable would blank its particles at once) and the
copy dies once its particles have (:data:`TAIL_PAD` past the longest
``maxAge`` among its systems' sinks).
This module reads those windows from the build's own ``characters.xbr``
(the clips W3, W22 and X10 play, the grown markers, the bound graphs)
and packs the table the shim reads (:func:`ring_plan`,
:meth:`Plan.pack`).

The body's own instance (+0x230) keeps its look but for the emitters a
copy shows (:attr:`Key.ops` list :data:`OWN`, written by value every
tick), so no effect draws twice; an E copy (mode :data:`E`) mutes its
ambient emitters (on at rest: the own instance shows them) and what only
a left-out clip switches (Balthazar's drain stream, which a copy spawned
in that clip's crossfade would draw: AZ-653), and hides its
platforms (the own instance's draw: ``gameVisible`` 0, or, where a link
drives that, ``lodVisibility`` 0, which the draw multiplies in; a STAND
copy's platform shown by its trigger alone keeps its lod, Step 2.155e), and
zeroes any platform's damage (a copy deals none: hits never travel,
D115).  The key is the body's own graph; with an emitter on at rest that
a clip carries (the air elemental's puff under ``m_turbulence``) it is
mode :data:`P`: one copy stays bound at all times and carries that
ambient look, the own instance's emitters all muted, and a throw arms it
(the cloud rides out as the owner played it, D429).

What a copy can't do is left out by name: a clip that turns on a switch
reaching a critter generator, an effect, a sound, a camera or a logic
switch (a copy would spawn or play it twice: guard_fire's own attack_2, its shards), or a
platform's damage (a copy would hit with it: Balthazar's drain), leaves
that row out, logged; an emitter nothing can stop is refused (D35).
With X37 installed (AZ-653, Step 2.153c) a clip whose only such platform
hangs under an inherit-mode-7 node (Balthazar's drain box, which X37
anchors on the drain's target) is a drain row: its copy plays the drain
bound, the platform's damage goes to 0 at the detach (:data:`DETACH`),
X37 keeps the copy's mode-7 nodes on the target, and each window its
switch drives closes by that switch (:attr:`Window.switch`) at its end.

A recipe's (or its weapon style's) shield and beam ``effects`` rows (Step
2.167c, D538's E3; :mod:`~azurik_mod.assets.fx_templates`) are BOUND keys
(mode :data:`BOUND`), one per row, after the body's own and stand keys:
each a graph of its own, :func:`bound_key`, built by
:func:`bound_graph` from the template's sets under its holder on the
empty :data:`HOST` (so no vanilla graph changes and no NPC plays it), in
one handle (:data:`BOUND_SLOTS`) past the own and stand keys' 16
(:data:`OWN_SHARE`).  At each entry of a column its row names the copy is
spawned bound (or, alive, re-armed) and its :data:`SHOW` writes go to
their values; at the next clip change, a hit or the death they fade to 0
over the row's ``fade`` (its ``hold_ms``) with the copy still bound, and it
dies its tail (the longest ``maxAge`` of its sinks + :data:`TAIL_PAD`, 0
with none) later.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from azurkit.tools.characters import fx_edit, fx_templates
from azurkit.tools.characters.characters import marker_records, read_body, track_value
from azurkit.tools.characters.retarget import named_clip
from azurkit.tools.characters.ports import link_curve, link_value
from azurkit.core.xbr.graph import Graph, Schema, bind_name, list_at
from azurkit.core.xbr.nodes import named_resources, parse_toc

E, P, STAND, BOUND = 0, 1, 2, 3
"""A key's mode: E, a copy spawned at each attack entry whose row names
it; P, one copy kept bound at all times, armed by a throw; STAND (D434,
Step 2.155), another graph's copy spawned dark at each entry of a clip
that carries it (its tail over 0), standing where the next clip change
detaches it, its :data:`HOLD` writes ramped up there, held and released
(:attr:`Key.hold_ms`); BOUND (Step 2.167c), an effects row's graph,
spawned at each entry of a clip that plays it (its tail over 0, or 0 and
its fade's: a shield's, with no particles) and kept bound, its
:data:`SHOW` writes at their values while that clip plays, faded over
``hold_ms`` once it doesn't."""
SPAWN, DELAY, ARM, OWN, HOLD, DETACH, SHOW = range(7)
"""An op's list: written on a copy once loaded; written 0 there and its
value once the crossfade is over (:attr:`Key.delay`); written at the arm;
on the body's own instance, by value, every tick: 0 while a bound armed
copy shows it, and for the crossfade and a tick after its detach (always,
for a P key), else its value (the authored one); on a detached STAND
copy, its value times the stand's level, every tick it changes; on a copy
at its detach (a drain row's platform damage, which its link rewrote
while bound: AZ-653); on a BOUND copy every tick, its value times its
level (1 while armed, falling to 0 over its fade)."""
COLUMNS = 24
ROWS = 2 * COLUMNS
"""A row per ``attacks_anims`` column, then one per X10 ring entry."""
KEYS = 5
"""The body's own graph, a stand and :data:`~azurik_mod.assets.fx_templates.BOUND_ROWS` bound keys."""
CLIPS = 16
SLOTS = 20
"""The ring's handles, every key's together."""
OWN_SHARE = 16
"""The own and stand keys' handles (the whole ring before Step 2.167c): a
recipe's ``slots`` and a stand's 5 fit in it, the bound keys' past it."""
BOUND_SLOTS = 1
"""A bound key's copies: one, re-armed while it lives."""
HOST = "characters/key_battery/fx/fx_default"
"""The empty graph (no record, its ndbg alone; in both releases) a bound
row's graph is a clone of: an :data:`ORIGIN` root, the holder under it,
the template's sets under that."""
ORIGIN = "effectOrigin"
"""The bind name of a bound row's graph's root (AZ-709, Step 2.167d): an
instance's binder takes the transform bound by this name as its root
(0x625D0) and sets its matrix to the wearer's model matrix every frame
(0x62C40's +0xC bit 29), as every vanilla shield's graph roots one
(``fx/magic/fx_shield_force1``: effectOrigin, m_root under it, the field
under that); a graph without one draws each node at its own transform
in the world, at the level's origin (Step 2.167c's sitting)."""
CENTRE = "m_root"
"""The marker a ``centre`` or ``front`` holder binds: garret4's own (the
game's shields hang under it), X16's on every other body (Step 2.118)."""
KEY_SLOTS = 12
"""The most a key's computed count takes."""
WINDOWS = 16
"""The most windows a clip has in one key (a slot's ramp table)."""
OPS = 96
WINS = 64
KEY_SIZE = 64
RIG_CLIPS = ("idle", "idle_1", "walk")
"""The clip whose keyed markers are the body's rig (a limb, a mouth, a
jaw: every clip moves them with the body): the first the body has."""
RIG_CLOSE = 0.33
"""s after the detach a rig emitter closes (its window's end if sooner)."""
RAMP_S = 10 / 30
"""s an emitter's rate takes to fade to 0 once its window closes."""
TAIL_PAD = 0.33
"""s past the longest ``maxAge`` before a copy whose windows are all
closed dies."""
DEFAULT_AGE = 2.0
"""A window's particle life when its system has no sink (s)."""
CARRY_MIN = 2.0
"""Model units a clip must move a marker from its rest for the
emitters under it to ride it (a carrier)."""
EMITTING = 0.1
"""Particles a second under which an emitter counts as off."""
SWITCH_ON = 0.01
STEP = 1 / 60
SLOT_CAP = (KEY_SLOTS, 4)
"""Slots per key: a graph of up to :data:`BIG` records, a bigger one
(the frame time a copy costs grows with its records: 2.145 S-D3)."""
BIG = 100
CHAIN_S = 0.5
"""s between two throws a key's slot count is sized for."""
EXCLUDED = ("critterGenerator", "effect", "soundEffect", "stereoSound", "camera", "switch", "levelSwitch",
            "gameState", "gameSaveControl", "rumble", "puppetMaster")
"""Node types a copy would run twice (spawn, play, switch the logic)."""
ENABLE, EMIT_RATE = 4, 5
LOD_VISIBLE, GAME_VISIBLE, GAME_SOLID, DAMAGE = 0, 10, 11, 17
SYSTEM_ENABLE = 4
EMITTERS = ("pEmitter", "pBurstEmitter")
SINK_AGE = 5
TRANSLATE = {1: 0, 2: 1, 3: 2}
"""A transform's translate plugs and the marker components they copy."""
TRANSLATE_Z = 3
BOUND_VISIBLE = 1 / 1024
"""gameVisible at which a stand's platform its trigger alone shows draws while its copy is bound, from the copy's
crossfade on (a :data:`DELAY` op; the trigger's own link writes 0 there until then): too faint to pass its
material's alpha test, but the draw asks for its mesh's and textures' load runs, each a frame after the one before
(the clone's appended entries are each their own run), so they are in before the let-go and its first presents
there are textured, not black (AZ-690)."""
STAND_SLOTS = 5
"""A stand key's copies unless ``fx_ring.stand.slots`` says: a held chain's four standing (one
stands every 1.6 s for 4.93 s, 4.43 s before Step 2.155e's 2.0 s hold) and the gust in flight, which every gust
spawns (AZ-671), so a chain's last gust always has one; taps that hold all five (one every 1.2 s, each let go by the
idle) end the oldest whose funnel has faded, so every gust stands its own (AZ-689)."""

_HEAD = struct.Struct("<BBHH2x")
_KEY = struct.Struct("<BBBBHHHH")
_CLIP = struct.Struct("<HHf")
_OP = struct.Struct("<HBBf")
_WIN = struct.Struct("<HHBBHf")
WIN_RIG, WIN_SWITCH = 1, 2
"""A window's flags: it closes on the rig; it closes by its switch."""
TABLE_SIZE = (_HEAD.size + ROWS + KEYS * _KEY.size + CLIPS * KEYS * _CLIP.size + KEYS * KEY_SIZE
              + OPS * _OP.size + WINS * _WIN.size)
"""The shim's ``Table`` (``fx_ring.c``): its size, which the bytes param
``player_model_fx_ring_table`` carries."""


@dataclass(frozen=True)
class Op:
    """A write: record ``record``'s attribute ``attr`` := ``value``."""

    record: int
    attr: int
    value: float
    list: int


@dataclass(frozen=True)
class Window:
    """An emitter of a clip's copy: ``record``, closed (``attr`` := 0 on
    ``target``: itself, or its system when both its enable and rate are
    linked) at clip time ``off``, or 0.33 s after the detach when ``rig``;
    a drain row's (AZ-653) by its ``switch`` instead: that transform's
    translateZ := 0 at ``off`` (its links take the emitter and the box to
    0), while another clip's copy closes it through ``target``."""

    record: int
    target: int
    attr: int
    rig: bool
    off: float
    switch: int | None = None


@dataclass(frozen=True)
class Key:
    """One graph the ring copies: its resource key, mode, slot share,
    record count (the shim's write guard), whether its :data:`DELAY` ops
    (its carried emitters; a stand's trigger-shown platform's
    :data:`BOUND_VISIBLE`, AZ-690) wait out the crossfade (``delay``: the
    shim writes them 0 for anim+0x14 and a tick after a spawn), its ops, and a STAND key's hold (ms its
    :data:`HOLD` writes stay at their value)."""

    name: str
    mode: int
    slots: int
    records: int
    delay: int
    ops: tuple[Op, ...]
    hold_ms: int = 0


@dataclass
class Plan:
    """The table of a build: its keys, each row's clip (an index into
    ``clips``, the rows with no copy left out), per clip and key its
    windows and tail (s), the rows left out (log lines), and per (clip,
    key) of a STAND key the clip ms its carrier leaves (the shim's
    ``ClipSpec.first``: a copy detached sooner stands nothing), and of a
    BOUND key 1 where the clip plays it, else 0."""

    keys: list[Key]
    rows: dict[int, int]
    clips: list[str]
    windows: list[list[tuple[tuple[Window, ...], float]]]
    left_out: list[str] = field(default_factory=list)
    leaves: dict[tuple[int, int], int] = field(default_factory=dict)

    @property
    def mask(self) -> int:
        """The columns (bit i) whose own row has a copy."""
        return sum(1 << r for r in self.rows if r < COLUMNS)

    def pack(self) -> bytes:
        """The shim's ``Table``, little-endian, :data:`TABLE_SIZE` bytes.
        :class:`ValueError` when the build's windows, ops or slots don't fit it."""
        ops = [op for key in self.keys for op in key.ops]
        for share, keys in ((OWN_SHARE, [k for k in self.keys if k.mode != BOUND]), (SLOTS, self.keys)):
            if sum(key.slots for key in keys) > share:
                raise ValueError(f"the fx ring holds {share} copies"
                                 + (" of the body's own and stand keys" if share == OWN_SHARE else "")
                                 + ": this build's keys ask " + " + ".join(f"{key.slots} ({key.name})" for key in keys))
        wins = [w for per in self.windows for ws, _ in per for w in ws]
        if len(self.keys) > KEYS or len(self.clips) > CLIPS or len(ops) > OPS or len(wins) > WINS or any(
                len(ws) > WINDOWS for per in self.windows for ws, _ in per):
            raise ValueError(f"the fx ring's table holds {KEYS} keys, {CLIPS} clips, {OPS} writes and {WINS} "
                             f"windows ({WINDOWS} a clip): this build has {len(self.keys)}, {len(self.clips)}, "
                             f"{len(ops)} and {len(wins)}")
        out = bytearray(_HEAD.pack(len(self.keys), len(self.clips), len(ops), len(wins)))
        out += bytes(self.rows.get(r, 0xFF) for r in range(ROWS))
        first = 0
        for k in range(KEYS):
            if k < len(self.keys):
                key = self.keys[k]
                out += _KEY.pack(key.mode, key.slots, key.delay, sum(x.slots for x in self.keys[:k]), key.records,
                                 first, len(key.ops), key.hold_ms)
                first += len(key.ops)
            else:
                out += bytes(_KEY.size)
        first = 0
        for c in range(CLIPS):
            for k in range(KEYS):
                if c < len(self.clips) and k < len(self.keys):
                    ws, tail = self.windows[c][k]
                    out += _CLIP.pack(self.leaves.get((c, k), first), len(ws), tail)
                    first += len(ws)
                else:
                    out += bytes(_CLIP.size)
        for k in range(KEYS):
            name = self.keys[k].name.encode("ascii") + b"\0" if k < len(self.keys) else b""
            if len(name) > KEY_SIZE:
                raise ValueError(f"the fx ring's key {self.keys[k].name!r} is past {KEY_SIZE - 1} characters")
            out += name.ljust(KEY_SIZE, b"\0")
        out += b"".join(_OP.pack(op.record, op.attr, op.list, op.value) for op in ops).ljust(OPS * _OP.size, b"\0")
        out += b"".join(_WIN.pack(w.record, w.target, w.attr, WIN_RIG * w.rig + WIN_SWITCH * (w.switch is not None),
                                  w.switch or 0, w.off) for w in wins).ljust(WINS * _WIN.size, b"\0")
        assert len(out) == TABLE_SIZE
        return bytes(out)


@dataclass(frozen=True)
class Bound:
    """A shield or beam ``effects`` row as X38 plays it (Step 2.167c): its
    graph's key (:func:`bound_key`) and record count, the
    ``attacks_anims`` columns (indices) whose entries play it, its
    :data:`SHOW` writes ((record, attribute, value): the template's
    ``show``), its fade (s) and its tail (s it lives past the fade: its
    particles' life)."""

    key: str
    records: int
    columns: tuple[int, ...]
    show: tuple[tuple[int, int, float], ...]
    fade: float
    tail: float


def bound_key(body: str, template: str, k: int) -> str:
    """The key of a build's ``k``-th bound row's graph (Step 2.167c),
    ``characters/<body>/v/fx/fx_<template>_<k>``: X38 spawns it by name, so
    no NPC plays it."""
    return f"characters/{body}/v/fx/fx_{template}_{k}".casefold()


def bound_graph(characters: bytes, xbe: bytes, fx_xbr: bytes, effect, key: str, base: int, *,
                marker: str | None = None, at: tuple[float, float, float] = (0.0, 0.0, 0.0), scale: float = 1.0,
                values: dict | None = None):
    """A bound ``effects`` row's graph (Step 2.167c): a clone of the empty
    :data:`HOST` (its new entries numbered from ``base``) with a
    ``holder`` graft its root (:data:`~azurik_mod.assets.fx_edit.ROOT`),
    bound by an ``anchor`` edit to :data:`ORIGIN` so the game puts it on
    the wearer (AZ-709), the template's holder under it and its sets under
    that (:class:`~azurik_mod.assets.fx_edit.Clone`'s grafts), the
    holder bound to ``marker`` by an ``anchor`` edit, else
    placed at ``at`` (model units), turned by the template's ``turn`` and
    scaled ``scale``; the template's edits, its params' record writes
    (``values``: the row's, each ``auto`` resolved by the build), its
    colour's writes and recolours, its show attributes 0 (X38 writes them
    up) and every platform's gameSolid and damage 0 (a look: no wall, no
    hit): the resources :func:`~azurik_mod.xbr.append.append_resources`
    adds, the graph's :class:`Bound` less its columns, and the clone's
    :meth:`~azurik_mod.assets.fx_edit.Clone.plan`.
    :class:`ValueError` names what the archives lack (D35)."""
    from azurkit.tools.characters._player_throw import colour_ramp
    t = effect.template
    values = effect.values if values is None else values
    clone = fx_edit.Clone(characters, HOST, xbe, base=base, fx_xbr=fx_xbr)
    if clone.recs:
        raise ValueError(f"its {t.name} row: {HOST} holds {len(clone.recs)} records, not 0: not a vanilla "
                         "characters.xbr")
    schema = clone.schema
    grafted = [(name, kind) for g in (fx_templates.HOLDER, fx_templates.HOLDER, *t.sets)
               for _, name, kind in fx_templates.GRAFTS[g].records]
    names: dict[str, tuple[int, str]] = {}   # a set name's record (the template's loader refuses a shared one),
    for n, (name, kind) in enumerate(grafted[1:], 1):   # the holder's its own [1], never the root's [0]
        names.setdefault(name, (n, kind))
    grafts = ([{"template": fx_templates.HOLDER, "parent": fx_edit.ROOT}, {"template": fx_templates.HOLDER, "parent": 0}]
              + [{"template": g, "parent": 1} for g in t.sets])
    holder = fx_templates.GRAFTS[fx_templates.HOLDER].records[0][1]
    edits = [{"record": 0, "name": holder, "type": "transform", "anchor": ORIGIN},
             {"record": 1, "name": holder, "type": "transform", "anchor": marker} if marker else
             {"record": 1, "name": holder, "type": "transform",
              "set": {**dict(zip(("translateX", "translateY", "translateZ"), at)),
                      **dict(zip(("rotateX", "rotateY", "rotateZ"), t.turn)),
                      **dict.fromkeys(("scaleX", "scaleY", "scaleZ"), scale)}}]

    def edit(name: str, **change) -> None:
        r, kind = names[name]
        edits.append({"record": r, "name": name, "type": kind, **change})
    for e in t.edits:
        edit(e["record"], **{k: v for k, v in e.items() if k != "record"})
    for pname, param in t.params.items():
        for w in param["writes"]:
            if "record" in w:
                edit(w["record"], set={w["attr"]: float(values[pname]) * w.get("factor", 1.0)})
    if t.colour is not None and effect.colour is not None:
        for w in t.colour.get("writes", []):
            edit(w["record"], set=dict(zip(w["attrs"], effect.colour)))
        for rc in t.colour.get("recolor", []):
            edit(rc["record"], texture={**({"stage": rc["stage"]} if "stage" in rc else {}),
                                        "recolor": {"ramp": colour_ramp(effect.colour)}})
    for sh in t.show:
        edit(sh["record"], set={sh["attr"]: 0.0})
    edits += [{"record": n, "name": name, "type": kind, "set": {"gameSolid": 0.0, "damage": 0.0}}
              for n, (name, kind) in enumerate(grafted) if kind == "platform"]
    try:
        clone.apply(edits, grafts)
    except ValueError as exc:
        raise ValueError(f"its {t.name} row: {exc}") from None
    plan = clone.plan()
    new = clone.build(key)
    ages = [struct.unpack_from("<f", clone.payload, list_at(clone.payload, clone.recs[r] + 8)[0] + 4 * SINK_AGE)[0]
            for r, kind in enumerate(clone.types) if kind == "pSink"]
    show = tuple((names[sh["record"]][0], schema.types[names[sh["record"]][1]].attrs.index(sh["attr"]),
                  float(sh["value"])) for sh in t.show)
    fade = next((float(values[p]) for p, param in t.params.items() if {"engine": "fade"} in param["writes"]), 0.0)
    return new, Bound(key, len(clone.recs), (), show, fade, round(max(ages) + TAIL_PAD, 4) if ages else 0.0), plan


class _Fx:
    """One key's graph against the body that binds it."""

    def __init__(self, characters: bytes, schema: Schema, key: str, body, rig: set[str]):
        toc = parse_toc(characters)
        index = next((i for i, n in named_resources(characters).items() if n.casefold() == key.casefold()), None)
        if index is None:
            raise ValueError(f"the fx ring's key {key!r} is not in characters.xbr")
        self.key, self.schema = key, schema
        self.g = g = Graph(characters, toc, toc[index], schema)
        self.rest = dict(marker_records(characters, body.name))
        bones = {name for name, _ in body.bones}
        self.bound: dict[int, tuple[str, str]] = {}
        for i, ro in enumerate(g.recs):
            if ro is not None and schema.is_a(g.types[i], "transform"):
                name = bind_name(g.s, ro)
                if name in self.rest:
                    self.bound[i] = ("marker", name)
                elif name in bones or name == "effectOrigin":
                    self.bound[i] = ("rig", name)
        self.rig = rig
        self.inc = g.incoming()
        self.systems: dict[int, int] = {}
        self.ages: dict[int, float] = {}
        for s, t in enumerate(g.types):
            if t != "pSystem":
                continue
            comps = self._components(s)
            ages = [g.attrs(c)[SINK_AGE] for c in comps if g.types[c] == "pSink"]
            for c in comps:
                self.systems[c] = s
            self.ages[s] = max(ages, default=DEFAULT_AGE)
        self.emitters = [i for i, t in enumerate(g.types) if t in EMITTERS]
        self.platforms = [i for i, t in enumerate(g.types) if t == "platform"]

    def _components(self, s: int) -> list[int]:
        ro = self.g.recs[s]
        count, ref = struct.unpack_from("<iI", self.g.s, ro + 0x30)
        if not 0 < count < 256:
            return []
        return [c for c in struct.unpack_from(f"<{count}I", self.g.s, ro + 0x34 + ref) if c < len(self.g.recs)]

    def links_into(self, i: int, attr: int) -> list:
        return [(lk, k) for lk, k in self.inc.get(i, []) if lk.dst_plug == attr]

    def value(self, i: int, attr: int, markers) -> float:
        """Record ``i``'s attribute with the bound transforms at ``markers``
        (marker name -> 12 values): each link from a bound transform's
        translate (the marker's position) delivers its value, the largest
        winning; any other source leaves the authored value."""
        authored = self.g.attrs(i)[attr]
        got = []
        for lk, k in self.links_into(i, attr):
            src = self.bound.get(lk.src)
            if src is None or src[0] != "marker" or lk.src_plug not in TRANSLATE:
                return authored
            x = markers[src[1]][TRANSLATE[lk.src_plug]]
            got.append(link_value(link_curve(self.g, lk.src, k), x, lk.weight, lk.factor))
        return max(got) if got else authored

    def emitting(self, i: int, markers) -> bool:
        """Whether emitter ``i`` emits with the bound transforms at
        ``markers``: on, at :data:`EMITTING` or more, and every switch
        driving it (a bound marker's translateZ) over :data:`SWITCH_ON`
        (the census's rule: firedrake's 0.01 is off)."""
        switches = [self.bound[lk.src][1] for a in (ENABLE, EMIT_RATE) for lk, _ in self.links_into(i, a)
                    if lk.src_plug == TRANSLATE_Z and self.bound.get(lk.src, ("",))[0] == "marker"]
        return (self.value(i, ENABLE, markers) > 0 and self.value(i, EMIT_RATE, markers) >= EMITTING
                and all(markers[name][2] > SWITCH_ON for name in switches))

    def carrier(self, i: int) -> tuple[str, str] | None:
        """The nearest bound transform over record ``i``: (kind, name)."""
        for a in (i, *self.g.ancestors(i)):
            if a in self.bound:
                return self.bound[a]
        return None

    def anchored(self, i: int) -> bool:
        """Whether record ``i`` hangs under an inherit-mode-7 transform,
        which the game places on the player (X37: on the drain's target)."""
        return any(self.schema.is_a(self.g.types[a], "transform") and self.g.xform_fields(a)["mode"] == 7
                   for a in self.g.ancestors(i))

    def is_rig(self, i: int) -> bool:
        """Whether ``i`` hangs from the body's rig (a bone, the critter, the
        root, or a marker its idle clip keys)."""
        owner = self.carrier(i)
        return owner is None or owner[0] == "rig" or owner[1] in self.rig

    def close(self, i: int) -> tuple[int, int]:
        """(record, attr) that stops emitter ``i`` and no link writes."""
        if not self.links_into(i, ENABLE):
            return i, ENABLE
        if not self.links_into(i, EMIT_RATE):
            return i, EMIT_RATE
        s = self.systems.get(i)
        if s is None or self.links_into(s, SYSTEM_ENABLE):
            raise ValueError(f"the fx ring: {self.key}'s emitter [{i}] {self.g.names[i]!r} has its enable, rate "
                             "and system all linked, so nothing can stop it")
        return s, SYSTEM_ENABLE

    def downstream(self, i: int, depth: int = 4) -> set[int]:
        out, todo = set(), [i]
        for _ in range(depth):
            todo = [lk.dst for r in todo for lk in self.g.links(r) if lk.dst not in out]
            out |= set(todo)
        return out


def _spans(ts, flags) -> list[tuple[float, float]]:
    out, start, prev = [], None, None
    for t, f in zip(ts, flags):
        if f and start is None:
            start = t
        if not f and start is not None:
            out.append((start, prev))
            start = None
        prev = t
    if start is not None:
        out.append((start, ts[-1]))
    return out


def _clip_markers(characters: bytes, body, clip: str, rest: dict):
    """``clip``'s marker values over its length, sampled at :data:`STEP`:
    (times, per time marker name -> 12 values)."""
    made = named_clip(characters, body.name, clip)
    tracks: dict[str, dict[int, object]] = {}
    for tr in made.markers:
        if 0 <= tr.target < len(body.markers):
            tracks.setdefault(body.markers[tr.target], {})[tr.comp] = tr
    n = max(2, int(made.length / STEP) + 2)
    ts = [min(made.length, k * STEP) for k in range(n)]
    frames = []
    for t in ts:
        frame = dict(rest)
        for name, comps in tracks.items():
            v = list(rest[name])
            for comp, tr in comps.items():
                got = track_value(*tr.modes, tr.keys, t)
                if got is not None:
                    v[comp] = got
            frame[name] = tuple(v)
        frames.append(frame)
    return ts, frames, set(tracks)


FADE_MAX = 65.535
"""s: the longest fade a bound key's ``hold_ms`` holds (u16 ms)."""


def ring_plan(characters: bytes, xbe: bytes, body, picks: dict[int, str], ring: list[str] | None = None,
              recipe: dict | None = None, drains: bool = False, bound: tuple[Bound, ...] = (),
              turns: int = 0, own: bool = True) -> Plan | None:
    """X38's table for a build: :func:`own_plan`'s (unless not ``own``: a
    build with no picks of its own) with ``bound``'s keys (Step 2.167c: a
    build's shield and beam rows, :class:`Bound`) after its own and stand
    keys, each in :data:`BOUND_SLOTS` handles, on the rows of its columns,
    and on X10's entry rows when one of them is in ``turns`` (X10's
    columns: they play its entries; so does any other column X10 turns); a
    row whose clip plays another set of bound keys than another row's
    gets a clip entry of its own.  ``None`` with neither."""
    base = own_plan(characters, xbe, body, picks, ring, recipe, drains) if own else None
    if not bound:
        return base
    base = base or Plan([], {}, [], [], [])
    for b in bound:
        if not 0.0 <= b.fade <= FADE_MAX:
            raise ValueError(f"the fx ring: {b.key}'s fade {b.fade:g} s is not from 0 to {FADE_MAX:g} s (the table "
                             "holds ms in 16 bits)")
    rotating = {j for j, b in enumerate(bound) if any(turns >> c & 1 for c in b.columns)}
    wanted = set(base.rows) | {c for b in bound for c in b.columns if c < COLUMNS}
    if rotating:
        wanted |= {COLUMNS + e for e in range(min(len(ring or ()), COLUMNS))}
    entries: dict[tuple[int | None, frozenset], int] = {}
    rows = {}
    for r in sorted(wanted):
        js = frozenset(j for j, b in enumerate(bound) if r in b.columns) if r < COLUMNS else frozenset(rotating)
        c = base.rows.get(r)
        if c is not None or js:
            rows[r] = entries.setdefault((c, js), len(entries))
    n = len(base.keys)
    clips, windows, leaves = [], [], {}
    for e, (c, js) in enumerate(entries):
        first = min(r for r, x in rows.items() if x == e)
        played = base.clips[c] if c is not None else picks.get(first, "") if first < COLUMNS else ring[first - COLUMNS]
        clips.append(played + "".join(f" +{bound[j].key.rsplit('/', 1)[-1]}" for j in sorted(js)))
        windows.append([*(base.windows[c] if c is not None else [((), 0.0)] * n),
                        *(((), bound[j].tail if j in js else 0.0) for j in range(len(bound)))])
        leaves |= {(e, k): ms for (x, k), ms in base.leaves.items() if x == c}
        leaves |= {(e, n + j): int(j in js) for j in range(len(bound))}
    keys = [*base.keys, *(Key(b.key, BOUND, BOUND_SLOTS, b.records, 0, tuple(Op(r, a, v, SHOW) for r, a, v in b.show),
                              round(1000 * b.fade)) for b in bound)]
    return Plan(keys, rows, clips, windows, base.left_out, leaves)


def own_plan(characters: bytes, xbe: bytes, body, picks: dict[int, str], ring: list[str] | None = None,
             recipe: dict | None = None, drains: bool = False) -> Plan | None:
    """X38's table for the body's own graph and a stand: ``body`` (read
    with its variant's and baked dirs) wearing ``characters`` (the built archive), each
    ``attacks_anims`` column of ``picks`` (index -> the built Anim; the
    roll left out) playing its clip, and X10's ``ring`` (each entry's
    clip) when installed, against the graph the player's critter plays:
    the build's clone ``v/fx/fx_default`` when it adds one (X40, Step
    2.157), else the body's own ``fx/fx_default``.
    ``recipe`` is the variant's ``fx_ring``
    (:func:`~azurik_mod.patches._player_variants.check_fx_ring`): its
    ``slots`` and ``arm`` (the body's own key's; with no ``slots`` its
    computed count is capped at the ring's 16 less the stand key's), and its ``stand``
    (D434, Step 2.155): a second key, that graph in mode :data:`STAND`
    (the player's clone of it, :func:`~azurik_mod.assets.fx_edit.stand_key`,
    when its ``fx`` edits it: Step 2.155b), whose ``trigger`` (a bound marker of the grown body) feeds emitters
    one bound marker carries; a clip that moves that carrier
    :data:`CARRY_MIN` or more spawns it (its tail the longest ``maxAge``
    of those emitters' systems + :data:`TAIL_PAD`, no windows), and its
    one :data:`HOLD` op writes the trigger's translateZ.  ``drains``
    (X37 installed, AZ-653) makes a clip whose only blocker is a damage
    platform under a mode-7 node a drain row (the module's doc).  ``None``
    without that graph; a plan with no rows when no row gets a copy.  :class:`ValueError` names a recipe write the graph can't take,
    a stand key or trigger the build lacks, an emitter nothing stops and
    a linked platform nothing hides (D35)."""
    recipe = recipe or {}
    stand = recipe.get("stand")
    names = {n.casefold() for n in named_resources(characters).values()}
    own = next((k for k in (fx_edit.clone_key(body.name), f"characters/{body.name}/fx/fx_default")
                if k.casefold() in names), None)
    keys = [own] if own else []
    if not keys or not picks:
        return None
    if stand:   # its graph, or the player's clone its fx edits (Step 2.155b)
        keys.append(fx_edit.stand_key(body.name) if stand.get("fx") else stand["key"])
    schema = Schema(xbe)
    rows = {i: clip for i, clip in picks.items() if i < COLUMNS}
    for e, clip in enumerate((ring or ())[:COLUMNS]):
        rows[COLUMNS + e] = clip
    attacks = set(rows.values())
    plain = read_body(characters, body.name)
    rest = dict(marker_records(characters, body.name))
    idle = next((c for c in RIG_CLIPS if plain is not None and c in plain.clips), None)
    rig = _clip_markers(characters, body, idle, rest)[2] if idle else set()
    fxs = [_Fx(characters, schema, k, body, rig) for k in keys]
    s_k = len(fxs) - 1 if stand else None   # the stand key's index
    if stand:
        sfx = fxs[s_k]
        trigger = next((i for i, (kind, name) in sfx.bound.items()
                        if kind == "marker" and name.casefold() == stand["trigger"].casefold()), None)
        if trigger is None:
            raise ValueError(f"fx_ring.stand.trigger: {sfx.key} binds no marker {stand['trigger']!r} of {body.name}")
        fed = [lk.dst for lk in sfx.g.links(trigger) if sfx.g.types[lk.dst] in EMITTERS]
        carriers = {sfx.carrier(e) for e in fed}
        if not fed or len(carriers) != 1 or next(iter(carriers)) is None or next(iter(carriers))[0] != "marker":
            raise ValueError(f"fx_ring.stand.trigger: {stand['trigger']!r} feeds no emitters one marker of "
                             f"{body.name} carries in {sfx.key}")
        carrier = next(iter(carriers))[1]
        stand_tail = round(max(sfx.ages.get(sfx.systems.get(e), DEFAULT_AGE) for e in fed) + TAIL_PAD, 4)
    at_rest = {k: [fx.emitting(i, rest) for i in fx.emitters] for k, fx in enumerate(fxs)}
    sampled = {}
    for clip in sorted(attacks):
        try:
            sampled[clip] = _clip_markers(characters, body, clip, rest)
        except ValueError:   # a clip the body doesn't hold (X12's timers): no fx of its own
            continue
    per_clip: dict[str, list[tuple[tuple[Window, ...], float]]] = {}
    carried: dict[int, set[int]] = {k: set() for k in range(len(fxs))}
    left: dict[int, set[Window]] = {k: set() for k in range(len(fxs))}   # a left-out clip's windows
    boxes: dict[int, set[int]] = {k: set() for k in range(len(fxs))}   # a drain row's platforms (AZ-653)
    leaves: dict[str, int] = {}   # per clip, the ms the stand key's carrier leaves
    left_out = []
    for clip, (ts, frames, keyed) in sampled.items():
        out = []
        reason = None
        rode: dict[int, set[int]] = {k: set() for k in range(len(fxs))}
        boxed: dict[int, set[int]] = {k: set() for k in range(len(fxs))}
        for k, fx in enumerate(fxs):
            moved = {}
            for name in keyed - rig:
                r = rest[name]
                far = [math.dist(f[name][:3], r[:3]) for f in frames]
                if max(far) >= CARRY_MIN:
                    last = max((j for j in range(1, len(ts))
                                if math.dist(frames[j][name][:3], frames[j - 1][name][:3]) > 1e-4), default=0)
                    moved[name] = ts[last]
            if k == s_k:   # no windows: it stands where the clip's carrier is let go
                if carrier in moved:
                    leaves[clip] = round(1000 * ts[min((j for j in range(1, len(ts)) if math.dist(
                        frames[j][carrier][:3], frames[j - 1][carrier][:3]) > 1e-4), default=0)])
                out.append(((), stand_tail if carrier in moved else 0.0))
                continue
            on_switches = set()
            for s, (kind, name) in fx.bound.items():
                if kind == "marker" and name in keyed and rest[name][2] <= SWITCH_ON and any(
                        f[name][2] > SWITCH_ON for f in frames) and fx.g.links(s):
                    on_switches.add(s)
            reached = set().union(*(fx.downstream(s) for s in on_switches)) if on_switches else set()
            types = {fx.g.types[r] for r in reached if fx.g.types[r] in EXCLUDED}
            hurts = [p for p in fx.platforms if any(lk.src in on_switches for lk, _ in fx.links_into(p, DAMAGE))]
            drained = drains and bool(hurts) and not types and all(fx.anchored(p) for p in hurts)   # AZ-653
            hit = [] if drained else sorted(types | {f"[{p}] {fx.g.names[p]} damage" for p in hurts})
            wins = []
            for j, e in enumerate(fx.emitters):
                owner = fx.carrier(e)
                if at_rest[k][j]:
                    if owner is None or owner[0] != "marker" or owner[1] not in moved:
                        continue
                    off = moved[owner[1]]   # carried: on until its carrier arrives
                    rode[k].add(e)
                else:
                    on = [fx.emitting(e, f) for f in frames]
                    spans = _spans(ts, on)
                    if not spans:
                        continue
                    off = spans[-1][1]
                    if owner is not None and owner[0] == "marker" and owner[1] in moved:
                        rode[k].add(e)
                target, attr = fx.close(e)
                switch = next((lk.src for a in (ENABLE, EMIT_RATE) for lk, _ in fx.links_into(e, a)
                               if lk.src in on_switches), None) if drained else None
                wins.append(Window(e, target, attr, fx.is_rig(e) and switch is None, round(off, 4), switch))
            if drained and wins:
                boxed[k] |= set(hurts)
            if hit and wins:
                reason = f"{fx.key} {', '.join(hit)}"
            tail = max((fx.ages.get(fx.systems.get(w.record), DEFAULT_AGE) for w in wins), default=0.0) + TAIL_PAD
            out.append((tuple(wins), round(tail, 4)))
        if reason:
            left_out.append(f"{clip} (it switches {reason}, which a copy would run twice or hit with)")
            for k, (ws, _) in enumerate(out):
                left[k] |= set(ws)
            continue
        if any(ws for ws, _ in out) or clip in leaves:
            per_clip[clip] = out
            for k, es in rode.items():
                carried[k] |= es
                boxes[k] |= boxed[k]
    clips = sorted(per_clip)
    table_rows = {r: clips.index(c) for r, c in rows.items() if c in per_clip}
    if not table_rows:
        return Plan([], {}, [], [], left_out)
    used = {k: {w.record for c in clips for w in per_clip[c][k][0]} for k in range(len(fxs))}
    p_mode = bool(carried[0] & {e for j, e in enumerate(fxs[0].emitters) if at_rest[0][j]})
    plan_keys = []
    for k, fx in enumerate(fxs):
        mode = STAND if k == s_k else P if p_mode else E
        ops: list[Op] = []
        for p in fx.platforms:
            a = fx.g.attrs(p)
            shown = fx.links_into(p, GAME_VISIBLE)
            # a stand's platform its trigger alone shows (Step 2.155e: the funnel mesh) is dark while bound (the
            # trigger 0 at rest) and shown by the HOLD writes; once the crossfade is over it draws at
            # BOUND_VISIBLE, so its load runs are in by the let-go (AZ-690)
            trigger_shown = bool(shown) and mode == STAND and all(lk.src == trigger for lk, _ in shown)
            if trigger_shown:
                ops.append(Op(p, GAME_VISIBLE, BOUND_VISIBLE, DELAY))
            if shown and not trigger_shown:
                # a switch shows it while bound: hidden by its lod instead
                if fx.links_into(p, LOD_VISIBLE):
                    raise ValueError(f"the fx ring: {fx.key}'s platform [{p}] {fx.g.names[p]!r} has its "
                                     "gameVisible and lodVisibility linked, so nothing can hide it on a copy")
                ops.append(Op(p, LOD_VISIBLE, 0.0, SPAWN))
            elif a[GAME_VISIBLE] > 0:
                ops.append(Op(p, GAME_VISIBLE, 0.0, SPAWN))
            if a[GAME_SOLID] > 0 or fx.links_into(p, GAME_SOLID):
                ops.append(Op(p, GAME_SOLID, 0.0, SPAWN))
            if a[DAMAGE] != 0 or fx.links_into(p, DAMAGE):
                ops.append(Op(p, DAMAGE, 0.0, SPAWN))
        if mode in (E, STAND):   # a stand copy: dark but for its HOLD writes
            closes = [fx.close(e) for j, e in enumerate(fx.emitters) if at_rest[k][j] and e not in used[k]]
            # AZ-653: what only a left-out clip switches (Balthazar's drain stream [44], through its pool [2]),
            # which a copy spawned in that clip's crossfade would draw; not a system a used window feeds
            fed = {fx.systems.get(e) for e in used[k]}
            closes += [(w.target, w.attr) for w in sorted(left[k], key=lambda w: w.record) if w.record not in used[k]
                       and (w.target == w.record or w.target not in fed)]
            ops += [Op(target, attr, 0.0, SPAWN) for target, attr in dict.fromkeys(closes)]
        for j, w in enumerate(recipe.get("arm", ()) if k == 0 else ()):
            r = w["record"]
            if r >= len(fx.g.recs) or fx.g.names[r] != w["name"]:
                raise ValueError(f"fx_ring.arm[{j}]: record {r} of {fx.key} is "
                                 f"{fx.g.names[r] if r < len(fx.g.recs) else None!r}, not {w['name']!r}")
            attrs = schema.types[fx.g.types[r]].attrs
            for plug, v in w["set"].items():
                if plug not in attrs:
                    raise ValueError(f"fx_ring.arm[{j}]: {fx.g.types[r]} [{r}] has no attribute {plug!r}")
                ops.append(Op(r, attrs.index(plug), float(v), ARM))
        ops += [Op(p, DAMAGE, 0.0, DETACH) for p in sorted(boxes[k])]   # AZ-653: its link rewrote it while bound
        if mode == STAND:
            ops.append(Op(trigger, TRANSLATE_Z, 1.0, HOLD))
        delay = int(bool(carried[k]) or any(o.list == DELAY for o in ops))
        for e in sorted(carried[k]):
            target, attr = fx.close(e)
            ops.append(Op(target, attr, fx.g.attrs(target)[attr], DELAY))
        # the own instance: 0 while a copy shows it, else as authored
        muted = used[k] | ({e for j, e in enumerate(fx.emitters) if at_rest[k][j]} if mode == P else set())
        for e in sorted(muted):
            target, attr = fx.close(e)
            ops.append(Op(target, attr, fx.g.attrs(target)[attr], OWN))
        life = max((w.off for c in clips for w in per_clip[c][k][0]), default=0.0) + max(
            (t for c in clips for _, t in [per_clip[c][k]]), default=0.0)
        cap = SLOT_CAP[len(fx.g.recs) > BIG]
        if mode == STAND:
            plan_keys.append(Key(fx.key, mode, int(stand.get("slots", STAND_SLOTS)), len(fx.g.recs), delay,
                                 tuple(ops), round(1000 * float(stand["hold"]))))
            continue
        if stand:   # the stand key's handles first, so a recipe with no slots fits the ring (AZ-671's 5)
            cap = min(cap, OWN_SHARE - int(stand.get("slots", STAND_SLOTS)))
        slots = int(recipe.get("slots", min(cap, math.ceil(life / CHAIN_S) + 1)))
        plan_keys.append(Key(fx.key, mode, slots, len(fx.g.recs), delay, tuple(ops)))
    return Plan(plan_keys, table_rows, clips, [per_clip[c] for c in clips], left_out,
                {(clips.index(c), s_k): ms for c, ms in leaves.items() if c in per_clip})

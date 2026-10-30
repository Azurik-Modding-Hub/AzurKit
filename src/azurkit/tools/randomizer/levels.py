"""The randomizer's level semantics and the extract behind
``azurik-mod rando db-extract`` (its handler is
:mod:`azurkit.tools.randomizer.rando_commands`).

:func:`extract` reads the vanilla ISO and returns the generated half of
the randomizer database: one JSON text per level (the 22 playable levels
and ``training_room``), committed as ``data/generated/<level>.json`` and
read back by the planner's loader, the one reader of the generated data
(:func:`azurkit.tools.randomizer.planner.loader.load_database`, which refuses
a non-integer number or a repeated key).  Its layout is
``docs/RANDOMIZER_DB.md`` §3 (format version 1, ``format`` key
``azurik-rando-generated/1``, the planner loader's own).  What it
holds: ids, debug names, kinds, counts, decoded values, file offsets of
the name fields (the writer's targets) and requirement strings derived
from decoded data.  What it never holds (RANDOMIZER_PLAN §4.4, D80, D87):
coordinates, transforms, raw records or game bytes.  Positions are
computed in memory for one relation only, ``near_locations``, and
dropped.

Ported on 2026-10-12 (Step R1.1) from the randomizer evidence's
``r0/tools`` (``logic.py``, ``prefabs.py``, ``census.py`` and
``db_extract.py`` at ``c05c912``), with three of R0's gaps fixed:

* e2's teleporter pair was missed: R0 grouped locators by a
  ``Teleporters`` name namespace, and e2's locators are bare
  ``TeleLocator1`` and ``TeleLocator2`` (only its combiners and
  renderers carry a ``Teleporters_`` prefix, under a
  ``TwoTeleporterSystem`` node).  Teleporter pairs are now found by
  their wiring, not by name.
* Every teleporter pair is AND-gated: a field pad sends the player to
  the far locator only once both ends' reset pads have latched their
  beams (except the ``Teleporters_AlwaysON`` pairs, whose beams start
  on).  Each teleporter now carries those ``routes``, decoded from its
  wiring.
* f1's ``levelSwitch3`` names ``f7``, which is not on the disc (AZ-290):
  an exit whose destination level isn't on the disc is left out of the
  exit table.

The rules, each from the R0 evidence (``wiring/REPORT.md``,
``thresholds/REPORT.md``):

* A location is a pickup critterGenerator (gem, obsidian, key, fragment,
  power, consumable).  Its yield: maxGenerated < 0 gives
  ``|maxGenerated| x points``, > 0 gives maxGenerated, 0 is unbounded
  (0x6FD40); ``on_load`` is ``enable`` (attribute 13) != 0, and a
  generator with ``enable`` 0 and no link into it never spawns
  (``dead``).
* The 4th air and fire fragments spawn from ``characters.xbr`` graphs 16
  and 21, so those two locations carry the characters.xbr id and the a6
  and f6 level generators are dead.
* Barrier and geode groups: damage platforms (a fourcc at +0x38 other
  than ``none``) grouped by their nearest ``…:all`` ancestor, else their
  namespace, else their own name; the element combination from
  config.xbr ``magic``; the minimum ``magic`` level from the platforms'
  ``magic`` links (through at most two combiners); persistence from the
  save list and a stored ``turnOff``.  ``level``, ``persist`` and
  ``requires`` are [inferred, static]: that ``magic`` carries the
  attack's level and that a stored ``turnOff`` makes a barrier close
  again are readings of the data.
* A combination's level is the minimum of its elements' levels, at most
  3 (0x838E0), so a barrier at level L needs every element of its combo
  at >= L.
* Key type: the u32 fourcc at the lock platform's +0x40, named by
  config.xbr ``critters_item_data`` ``invType``; a lock uses up one key
  (0x58AD0).
* Seals, obsidian locks and the disc teleports come from their gameState
  link curves; a link's ``when`` is evaluated over the variable's own
  domain (:func:`nonzero_when`).
* An exit's arrival follows the engine's spot lookup (0x54172 calls
  0x5FF70): the first playerLocation of the destination's main graph
  whose record +0x1C string equals the spot or the spot + ``Shape``
  (case-sensitive), else the same for ``startspot``, else the origin.

The link and curve rules (USA VAs): per-frame propagation 0x663B0 sets
``target[dst] = curve(source[src] * weight) * factor`` (the curve skipped
when the link has none); the curve copy 0xD87E0 and evaluator 0xD8300
read ``{u16 pre, u16 post, u32 n (low 28 bits), i32 ref}`` and n keys
``{x, y, inTan, outTan}``, where an outTan above FLT_MAX holds y (a step)
and anything else is a cubic Hermite; a combiner (0x69BF0 / 0x69C10)
reads all n inputs, linked or not, with its function code at record
+0x1C.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import os
import re
import shutil
import struct
import tempfile
from pathlib import Path

from azurkit.tools.randomizer.planner.loader import FORMATS
from azurkit.tools.randomizer.art import nodes
from azurkit.core.xbr.nodes import parse_toc

GENERATED = Path(__file__).with_name("data") / "generated"
"""The committed generated data, one ``<level>.json`` per level."""

FORMAT = FORMATS["generated"]
GENERATOR = "azurik-mod rando db-extract"
RULES_DATE = "2026-10-12"
"""The date of the extraction rules, written into each file's ``_meta``."""

LEVELS = ("a1", "a3", "a5", "a6", "airship", "w1", "w2", "w3", "w4", "f1", "f2", "f3", "f4", "f6",
          "e2", "e5", "e6", "e7", "d1", "d2", "town", "life", "training_room")
"""The 22 playable levels and ``training_room``, in the census's order."""

LEVEL_KIND = {"town": "hub", "life": "realm", "training_room": "tutorial", "airship": "boss"}
GEMS = ("obsidian", "sapphire", "emerald", "ruby", "diamond")
BOSSES = ("guard_air", "guard_earth", "guard_fire1", "guard_fire2", "guard_fire3", "guard_water",
          "balthazar", "spideyzar")
ELEMENT_LETTER = {"E": "earth", "A": "air", "F": "fire", "W": "water"}
GS_COUNTER = {"air fragments": "disca", "water fragments": "discw", "fire fragments": "discf",
              "earth fragments": "disce", "life fragments": "discl",
              "air level": "air", "water level": "water", "fire level": "fire", "earth level": "earth",
              "obsidians": "obsidian", "sapphires": "sapphire", "emeralds": "emerald", "rubies": "ruby",
              "diamonds": "diamond"}
# The count-triggered levelSwitches to town and the guardian slots (RQ-4 / D81).  life has none (its
# exits are gated by a beam puzzle and the life_disk_placed latch); w1 has one (BossDefeated: water
# fragments >= 4, no placed check).
DISC_TELEPORT = {("a6", "PlaceAirDisk_levelSwitch"): "air", ("w3", "PlaceWaterDisk_levelSwitch"): "water",
                 ("f6", "PlaceFireDisk_levelSwitch"): "fire", ("e5", "DiskReplaced_levelSwitch"): "earth",
                 ("w1", "BossDefeated_levelSwitch"): "water"}
CHARACTER_SLOTS = {"a6": (16, "frag_air_4"), "f6": (21, "frag_fire_4")}
SLOT_BOSS = {"a6": "guard_air", "f6": "guard_fire3"}
GUARDIAN_SLOT = {"a6": "frag_air_4", "w3": "frag_water_4", "f6": "frag_fire_4", "e5": "frag_earth_4",
                 "life": "frag_life_4"}
SHORT_FN = {1: "plus", 2: "minus", 3: "mul", 4: "max", 5: "min", 6: "or", 7: "and", 8: "xor", 9: "not",
            10: "select", 11: "fn11", 12: "nand", 13: "nor", 14: "xnor", 15: "fn15"}
LOGIC_TYPES = {"switch", "combiner", "timer", "latch", "mathNode", "damper", "randomNumber", "blendWeighted",
               "gameState"}
POSITIONAL = re.compile(r"translate|rotate|scale|Pivot|localPosition")
# An exit is live when its gate reaches at least one input the game can change (a platform event, a
# counter, a global, a death, a teleport arrival, a moving part, a timer, or a switch's stored constant).
SOURCE_ATOM = re.compile(r"(touch|actionButton|key|magic|whack)\(|gs\[|global\[|numDead\(|teleported\(|pos\(|timer\[|=const")
GEODE = re.compile(r"(Diamond|Emerald|Ruby|Sapphire)Stone", re.I)


# --------------------------------------------------------------------------- curves and combiners
FLT_MAX = 3.4028234663852886e38


def combine(fn: int, ins: list[float], index: float = 0) -> float:
    """A combiner's output for function ``fn`` over its inputs (0x69C10)."""
    n = len(ins)
    if fn == 1:
        return float(sum(ins))
    if fn == 2:
        if n == 0:
            return 0.0
        if n == 1:
            return -ins[0]
        return ins[0] - sum(ins[1:])
    if fn == 3:
        p = 1.0
        for v in ins:
            p *= v
        return p
    if fn == 4:
        return max(ins) if ins else 0.0
    if fn == 5:
        return min(ins) if ins else 0.0
    if fn == 6:
        return next((v for v in ins if v != 0.0), 0.0)
    if fn == 7:
        return 1.0 if all(v != 0.0 for v in ins) else 0.0
    if fn == 8:
        return float(sum(1 for v in ins if v != 0.0) % 2)
    if fn == 9:
        return 1.0 if (n == 0 or ins[0] == 0.0) else 0.0
    if fn == 10:
        return ins[min(max(int(index), 0), n - 1)] if n else 0.0
    if fn == 12:
        return 1.0 if any(v == 0.0 for v in ins) else 0.0
    if fn == 13:
        return 1.0 if all(v == 0.0 for v in ins) else 0.0
    if fn == 14:
        return float(1 - sum(1 for v in ins if v != 0.0) % 2)
    raise ValueError(f"combiner function {fn} is not modelled")


class Curve:
    """The link curve a link's curve field (at section offset ``field_off``) points at."""

    def __init__(self, s: bytes, field_off: int):
        ref = struct.unpack_from("<i", s, field_off)[0]
        h = field_off + ref
        kind, n, kref = struct.unpack_from("<IIi", s, h)
        self.pre, self.post = kind & 0xFFFF, kind >> 16
        self.n = n & 0x0FFFFFFF
        kt = h + 8 + kref
        self.keys = [struct.unpack_from("<4f", s, kt + 16 * k) for k in range(self.n)]

    def __call__(self, x: float) -> float:
        ks = self.keys
        x0, xl = ks[0][0], ks[-1][0]
        if x < x0:
            if self.pre == 0:
                return ks[0][1]
            if self.pre == 1:
                return (x - x0) * ks[0][2] + ks[0][1]
            raise ValueError(f"pre-infinity mode {self.pre} is not modelled")
        if x >= xl:
            if self.post == 0:
                return ks[-1][1]
            if self.post == 1:
                sl = ks[-1][3] if math.isfinite(ks[-1][3]) else 0.0
                return (x - xl) * sl + ks[-1][1]
            raise ValueError(f"post-infinity mode {self.post} is not modelled")
        i = 0
        for k in range(len(ks) - 1):
            if ks[k][0] <= x:
                i = k
        (xa, ya, _, outa), (xb, yb, inb, _) = ks[i], ks[i + 1]
        if outa > FLT_MAX:
            return ya
        dx = xb - xa
        t = (x - xa) / dx
        m0 = dx * outa
        m1 = dx * inb if math.isfinite(dx * inb) else 0.0
        return (((2 * (ya - yb) + m1 + m0) * t + (3 * (yb - ya) - 2 * m0 - m1)) * t + m0) * t + ya


def link_curve(g: nodes.Graph, i: int, k: int) -> Curve | None:
    """The curve of record ``i``'s k-th link, or ``None`` (curve word 1)."""
    st, _ = g.list_at(i, 0x10)
    lo = st + 24 * k
    curve = struct.unpack_from("<I", g.s, lo + 4)[0]
    return None if curve == 1 else Curve(g.s, lo + 4)


def link_value(cv: Curve | None, x: float, weight: float, factor: float) -> float:
    """The value a link delivers for source value x (0x663B0)."""
    return (cv(x * weight) if cv is not None else x * weight) * factor


# gameState 0x711C0 fills each value slot by its variable's case (byte table 0x714CC, jump table 0x71498):
#   integer sources (a fild of an i32, a sum of 1.0s or a constant): health, health max, the inventory
#     slot values and caps, the four levels, current day, the five fragment counts, armor type and damage
#     type (constants), armor level and damage level;
#   real sources: day night timer = frac(clock) (two fmods by 1.0 at 0x71260, so [0, 1)) and armor
#     fraction = the f32 armor_mgr+0x24 (fld at 0x7145D; its range [0, 1] is [inferred]).
REAL_DOMAIN = {"day night timer": (0.0, 1.0, False), "armor fraction": (0.0, 1.0, True)}  # (lo, hi, hi included)


def _int_domain(var: str, cv: Curve | None, weight: float) -> range:
    v = var.lower()
    if v.endswith("fragments"):
        return range(0, 5)   # held counts can't leave 0-4
    if v in ("earth level", "air level", "fire level", "water level"):
        return range(0, 7)   # levels 4-6 show a higher count
    hi = 120 if v in ("emeralds", "diamonds", "rubies", "sapphires", "obsidians") else 10
    if cv is not None and weight:
        xs = [abs(k[0]) for k in cv.keys if math.isfinite(k[0])]
        if xs:   # past the last key the curve is its post mode, so one step beyond it is enough
            hi = max(hi, min(1000, int(math.ceil(max(xs) / abs(weight))) + 1))
    return range(0, hi + 1)


def _int_text(xs: list[int], nz: list[int]) -> str:
    if not nz:
        return "never"
    if len(nz) == len(xs):
        return "always"
    lo, hi = min(nz), max(nz)
    if nz == list(range(lo, xs[-1] + 1)):
        return f">={lo}"
    if nz == list(range(xs[0], hi + 1)):
        return f"<={hi}"
    return "in{" + ",".join(map(str, nz)) + "}"


def _real_text(cv, weight, factor, lo, hi, hi_incl) -> str:
    """Exact for step curves and plain links; a Hermite segment that changes
    sign inside is sampled, and the result is prefixed with '~'."""
    def val(x):
        return link_value(cv, x, weight, factor) != 0.0
    bps = {lo, hi}
    if cv is not None and weight:
        for k in cv.keys:
            if math.isfinite(k[0]) and lo < k[0] / weight < hi:
                bps.add(k[0] / weight)
    elif cv is None and lo < 0.0 < hi:
        bps.add(0.0)
    pts = sorted(bps)
    approx = False
    runs = []   # (a, a_closed, b, b_closed) of non-zero stretches

    def add(a, ac, b, bc):
        if runs and runs[-1][2] == a and (runs[-1][3] or ac):
            runs[-1] = (runs[-1][0], runs[-1][1], b, bc)
        else:
            runs.append((a, ac, b, bc))

    for a, b in zip(pts, pts[1:]):
        if val(a):
            add(a, True, a, True)
        inner = [val(a + (b - a) * t / 33.0) for t in range(1, 33)]
        if all(inner):
            add(a, False, b, False)
        elif any(inner):
            approx = True
            n = 400
            for t in range(1, n):
                x0, x1 = a + (b - a) * (t - 0.5) / n, a + (b - a) * (t + 0.5) / n
                if val(a + (b - a) * t / n):
                    add(round(x0, 4), True, round(x1, 4), True)   # closed so that neighbours merge
    if hi_incl and val(hi):
        add(hi, True, hi, True)
    runs = [r for r in runs if r[0] != r[2] or (r[1] and r[3])]
    if not runs:
        return "never"
    if len(runs) == 1 and runs[0][0] == lo and runs[0][1] and runs[0][2] == hi and (runs[0][3] or not hi_incl):
        return "always"
    out = []
    for a, ac, b, bc in runs:
        if a == b:
            out.append("{" + f"{a:g}" + "}")
        else:
            out.append(("[" if ac else "(") + f"{a:g},{b:g}" + ("]" if bc else ")"))
    return ("~" if approx else "") + "|".join(out)


def nonzero_when(cv: Curve | None, weight: float, factor: float, var: str) -> str:
    """Where on the variable's own domain a gameState link is non-zero: for
    an integer variable ``never``, ``always``, ``>=N``, ``<=N`` or ``in{a,b}``;
    for a real one (:data:`REAL_DOMAIN`) a union of intervals such as
    ``[0.25,0.75)``, or ``never`` / ``always``."""
    v = var.lower()
    if factor == 0.0:
        return "never"
    if v in REAL_DOMAIN:
        lo, hi, inc = REAL_DOMAIN[v]
        return _real_text(cv, weight, factor, lo, hi, inc)
    xs = list(_int_domain(var, cv, weight))
    return _int_text(xs, [x for x in xs if link_value(cv, float(x), weight, factor) != 0.0])


def combiner_header(g: nodes.Graph, i: int) -> tuple[int, int]:
    """(input count, function code) of a combiner record (record +0x18, +0x1C; 0x69BF0)."""
    return struct.unpack_from("<II", g.s, g.recs[i] + 0x18)


def gamestate_vars(g: nodes.Graph, i: int) -> dict[int, str]:
    """value slot -> variable name of a gameState record: ten (length, ref)
    names from record +0x18, which 0x71160 looks up case-insensitively in
    the XBE's 31-name table at 0x1A9D30."""
    ro = g.recs[i]
    out = {}
    for k in range(10):
        if struct.unpack_from("<I", g.s, ro + 0x18 + 8 * k)[0]:
            nm = g.pstr(ro, 0x18 + 8 * k)
            if nm:
                out[k] = nm
    return out


# --------------------------------------------------------------------------- prefab instances
COSMETIC_TYPES = {"soundEffect", "stereoSound", "pEmitter", "pBurstEmitter", "pRenderer", "pRendererB", "pSystem",
                  "pSink", "pBoxSink", "pGravity", "pVortex", "pAccelerator", "pNull", "effect", "effectControl",
                  "camera", "light", "shader", "rumble", "polyTrail", "puppetMaster"}
PLATFORM_TERMINAL = {"gameSolid": "collision", "gameVisible": "visibility", "lodVisibility": "visibility",
                     "damage": "damage", "climbable": "collision", "touch": "collision", "magic": "collision",
                     "key": "collision", "springboard": "collision", "autoSpring": "collision",
                     "water": "collision"}
TYPE_TERMINAL = {"levelSwitch": "exit", "playerLocation": "teleport", "gameSaveControl": "save",
                 "critterGenerator": "spawn", "helpnode": "help", "worldLocator": "locator"}
PREFAB_NS = {"keylock": re.compile(r"_keylock\d*$"), "keylordSystem": re.compile(r"^keylordSystem\d*$")}


def prefab_ns(name: str | None, word: str) -> str | None:
    """A keylock or keylordSystem instance's Maya namespace: the name up to
    and including the first ``:`` component that matches the prefab."""
    if not name:
        return None
    parts = name.split(":")
    for k, p in enumerate(parts[:-1]):
        if PREFAB_NS[word].search(p):
            return ":".join(parts[:k + 1])
    return None


def _terminal_class(g: nodes.Graph, i: int, plug: str) -> str:
    t = g.types[i]
    if t in COSMETIC_TYPES:
        return "cosmetic"
    if t == "platform":
        return PLATFORM_TERMINAL.get(plug, "platform:" + plug)
    if g.schema.is_a(t, "transform"):
        return "visibility" if plug in ("visibility", "lodVisibility") else "motion"
    return TYPE_TERMINAL.get(t, t)


def _downstream(g: nodes.Graph, start: list[nodes.Link], depth: int = 8) -> dict[str, set]:
    """{terminal class: {"name.plug"}} reached from ``start`` through logic nodes."""
    seen, terms = set(), collections.defaultdict(set)
    frontier = list(start)
    for _ in range(depth):
        nxt = []
        for lk in frontier:
            dst, plug = lk.dst, g.plug_name(lk.dst, lk.dst_plug)
            if (dst, plug) in seen:
                continue
            seen.add((dst, plug))
            if g.types[dst] in LOGIC_TYPES:
                nxt.extend(g.links(dst))
            else:
                terms[_terminal_class(g, dst, plug)].add(f"{g.names[dst]}.{plug}")
        frontier = nxt
    return terms


def fourcc(u: int) -> str | None:
    if u == 0:
        return None
    s = struct.pack("<I", u).rstrip(b"\0")
    return s.decode("ascii") if s and all(32 <= c < 127 for c in s) else f"#{u:#x}"


def classify(crit: str) -> tuple[str | None, str]:
    """(location class, base item) of a critterGenerator's critter name;
    the class is ``None`` for anything that isn't a pickup."""
    base = crit[:-5] if crit.endswith("_move") else crit
    if base == "obsidian":
        return "obsidian", base
    if base in GEMS:
        return "gem", base
    if crit.startswith(("key_", "frag_", "power_")):
        return "major", crit
    if crit.startswith(("small_", "large_", "all_")):
        return "consumable", crit
    return None, crit


def ns_of(name: str | None) -> str | None:
    """The Maya namespace: everything before the last ``:``."""
    return name.rsplit(":", 1)[0] if name and ":" in name else None


class _Ctx:
    """One node graph with the file context the extractor needs."""

    def __init__(self, stem: str, gi: int, g: nodes.Graph):
        self.stem, self.gi, self.g = stem, gi, g
        self.saved = set(g.saved())
        self.inc = g.incoming()   # dst -> [(link, k-th link of its source)]

    def gid(self, i: int) -> str:
        return f"{self.stem}/g{self.gi}/r{i}"

    def name(self, i: int) -> str:
        return self.g.names[i] or f"#{i}"

    def into(self, i: int, plug: str) -> list[tuple[nodes.Link, int]]:
        return [(lk, k) for lk, k in self.inc.get(i, []) if self.g.plug_name(i, lk.dst_plug) == plug]


# --------------------------------------------------------------------------- gate explanation (display hints)
def _step_condition(cv: Curve, xs: list[int]) -> str:
    """Hint text for a non-gameState source: the integers in xs where the curve is non-zero."""
    return _int_text(list(xs), [x for x in xs if cv(float(x)) != 0.0])


def explain(c: _Ctx, gs_names: dict, dst: int, plug: str, depth: int = 0, seen: set | None = None) -> str:
    """A display string for what drives (dst, plug), walked back through
    logic nodes up to 6 deep.  Mostly a hint, with one reader: an exit's
    ``live`` is whether its hint names a source atom (:data:`SOURCE_ATOM`),
    so a change to the hint's wording can change ``live`` (the vanilla
    equality test shows it as a data diff)."""
    g = c.g
    seen = set() if seen is None else seen
    parts = []
    for lk, k in c.inc.get(dst, []):
        if g.plug_name(dst, lk.dst_plug) != plug:
            continue
        s, sp = lk.src, g.plug_name(lk.src, lk.src_plug)
        st = g.types[s]
        cv = link_curve(g, s, k)
        nm = c.name(s)
        if st == "gameState":
            var = gs_names.get((c.gi, s), {}).get(lk.src_plug, f"value{lk.src_plug}")
            parts.append(f"gs[{var}]{nonzero_when(cv, lk.weight, lk.factor, var)}")
            continue
        if g.schema.is_a(st, "transform") and POSITIONAL.search(sp):
            parts.append(f"pos({nm}.{sp})")   # positional source: no interval is written
            continue
        cond = ""
        if cv is not None:
            try:
                cond = _step_condition(cv, list(range(0, 11)))
                cond = "" if cond == ">=1" else f"{{{cond}}}"
            except ValueError:
                cond = "{curve}"
        if lk.weight != 1.0 or lk.factor != 1.0:
            cond += f"{{w={lk.weight:g},f={lk.factor:g}}}"
        if st == "latch":
            gname = g.pstr(g.recs[s], 0x18)
            parts.append(f"global[{gname}]{cond}" if gname else f"latch[{nm}]{cond}")
            continue
        if st == "platform":
            parts.append(f"{sp}({nm}){cond}")
            continue
        if st == "critterGenerator":
            parts.append(f"{sp}({g.pstr(g.recs[s], 0x1C)}@{nm}){cond}")
            continue
        if st == "playerLocation":
            parts.append(f"{sp}(spot {nm}){cond}")
            continue
        if depth >= 6 or s in seen or st not in LOGIC_TYPES:
            parts.append(f"{st}:{nm}.{sp}{cond}")
            continue
        seen.add(s)
        if st == "combiner":
            n, fn = combiner_header(g, s)
            vals = g.attrs(s)
            ins = []
            for q in range(n):
                sub = explain(c, gs_names, s, f"inputs[{q}]", depth + 1, seen)
                ins.append(sub if sub else f"{vals[q]:g}")
            parts.append(f"{SHORT_FN.get(fn, fn)}({', '.join(ins)}){cond}")
        elif st == "switch":
            a = g.attrs(s)
            sub = []
            for p, idx in (("on", "turnOn"), ("off", "turnOff"), ("toggle", "toggle")):
                e = explain(c, gs_names, s, idx, depth + 1, seen)
                if e:
                    sub.append(f"{p}={e}")
                elif a[{"turnOn": 1, "turnOff": 2, "toggle": 3}[idx]] != 0.0:
                    sub.append(f"{p}=const")
            parts.append(f"switch[{nm}]{{{'; '.join(sub)}}}.{sp}{cond}")
        elif st == "timer":
            e = explain(c, gs_names, s, "enable", depth + 1, seen)
            parts.append(f"timer[{nm}]({e or 'stored'}).{sp}{cond}")
        else:
            parts.append(f"{st}:{nm}.{sp}{cond}")
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else "links(" + ", ".join(parts) + ")"


# --------------------------------------------------------------------------- decoded relations
def resolve_arrival(table: dict, spot: str | None) -> tuple[str | None, str]:
    """(playerLocation id, how) for a level request's spot: 0x5FF70 returns
    the first playerLocation of the main graph, in record order, whose
    +0x1C string equals the spot or the spot + ``Shape`` (case-sensitive;
    a NULL spot matches nothing); on a miss 0x54190 retries with
    ``startspot``; on a second miss 0x541B0 places the player at the
    origin.  ``how`` is ``spot``, ``spot+Shape``, ``startspot`` or ``origin``."""
    def find(s):
        if s is None:
            return None, None
        for gid, nm in table["locs"]:
            if nm == s:
                return gid, "exact"
            if nm == s + "Shape":
                return gid, "shape"
        return None, None
    gid, how = find(spot)
    if gid:
        return gid, "spot" if how == "exact" else "spot+Shape"
    gid, _ = find("startspot")
    return (gid, "startspot") if gid else (None, "origin")


def magic_level(c: _Ctx, i: int) -> list[tuple[int, str, int | None]]:
    """(target, plug, the smallest level 1-4 that turns it on, or None) for
    each ``magic`` link of a damage platform, followed through at most two
    combiners."""
    g = c.g
    found = []
    for k, lk in enumerate(g.links(i)):
        if g.plug_name(i, lk.src_plug) != "magic":
            continue
        cv = link_curve(g, i, k)
        targets = {}
        for L in (1, 2, 3, 4):
            v = (cv(L * lk.weight) if cv else L * lk.weight) * lk.factor
            frontier = [(lk.dst, lk.dst_plug, v)]
            for _ in range(3):
                nxt = []
                for dst, dplug, val in frontier:
                    if g.types[dst] == "combiner":
                        n, fn = combiner_header(g, dst)
                        ins = list(g.attrs(dst)[:n])
                        for q in range(n):
                            if any(l2.dst_plug == q for l2, _ in c.inc[dst]):
                                ins[q] = 0.0
                        if dplug < n:
                            ins[dplug] = val
                        try:
                            outv = combine(fn, ins)
                        except ValueError:
                            continue
                        for k2, l2 in enumerate(g.links(dst)):
                            if g.plug_name(dst, l2.src_plug) != "output":
                                continue
                            c2 = link_curve(g, dst, k2)
                            nxt.append((l2.dst, l2.dst_plug, (c2(outv * l2.weight) if c2 else outv * l2.weight) * l2.factor))
                    else:
                        targets.setdefault((dst, dplug), {})[L] = val
                frontier = nxt
        for (dst, dplug), lv in targets.items():
            on = [L for L, v in sorted(lv.items()) if v not in (None, 0.0)]
            found.append((dst, g.plug_name(dst, dplug), on[0] if on else None))
    return found


def requires_for_damage(combo: str | None, level: int | None) -> str | None:
    if not combo or level is None:
        return None
    return " & ".join(f"{ELEMENT_LETTER[ch]}>={level}" for ch in combo)


def _gate_and(c: _Ctx, loc: int) -> int | None:
    """The and-combiner that turns on the switch driving a playerLocation's
    ``teleport``, or ``None`` when its teleport isn't gated that way."""
    g = c.g
    ins = c.into(loc, "teleport")
    if len(ins) != 1 or g.types[ins[0][0].src] != "switch":
        return None
    on = c.into(ins[0][0].src, "turnOn")
    if len(on) != 1 or g.types[on[0][0].src] != "combiner" or combiner_header(g, on[0][0].src)[1] != 7:
        return None
    return on[0][0].src


def _bounce_guard(c: _Ctx, src: int) -> list[int]:
    """The playerLocations a nand-combiner reads ``teleported`` from (the
    teleporter prefab's guard against sending the player straight back),
    or ``[]`` when ``src`` is anything else."""
    g = c.g
    if g.types[src] != "combiner" or combiner_header(g, src)[1] != 12 or not c.inc.get(src):
        return []
    if not all(g.types[x.src] == "playerLocation" and g.plug_name(x.src, x.src_plug) == "teleported"
               for x, _ in c.inc[src]):
        return []
    return [x.src for x, _ in c.inc[src]]


def top_group(g: nodes.Graph, i: int) -> str | None:
    """A damage platform's barrier group (the census grouping): its nearest
    ancestor (or itself) named ``<ns>:all`` or ``all``, else its namespace."""
    for a in [i] + g.ancestors(i):
        nm = g.names[a] or ""
        if nm.endswith(":all") or nm == "all":
            return nm[:-4] if nm.endswith(":all") else nm
    return ns_of(g.names[i])


def _pivot(g: nodes.Graph, i: int):
    """Where a DAG record sits: its own (or its transform parent's) rotate
    pivot in world space.  In memory only, for ``near_locations``."""
    if g.schema.is_a(g.types[i], "transform"):
        return nodes.apply(g.world(i)[0], g.xform_fields(i)["rp"])
    p = g.parent(i)
    if p is not None and g.schema.is_a(g.types[p], "transform"):
        return nodes.apply(g.world(p)[0], g.xform_fields(p)["rp"])
    return nodes.apply(g.world(i)[0], (0.0, 0.0, 0.0))


def _gen_points(g: nodes.Graph, i: int) -> list:
    """A generator's spawn points in world space (0x6F960: the parent's
    matrix times each point).  In memory only, for ``near_locations``."""
    st, n = g.list_at(i, 0x2C)
    p = g.parent(i)
    m = g.world(p)[0] if p is not None else nodes.IDENTITY
    return ([nodes.apply(m, struct.unpack_from("<3f", g.s, st + 12 * q)) for q in range(min(n, 200))]
            or [nodes.apply(m, (0, 0, 0))])


def teleporter_pairs(c: _Ctx) -> list[list[int]]:
    """The teleporter pairs of a graph, found by their wiring, not their
    names: each locator's ``teleport`` is gated by an and-combiner that
    guards against the other locator's ``teleported``.  (A name rule
    misses e2's pair, whose locators have no namespace.)"""
    g = c.g
    parent: dict[int, int] = {}

    def root(i):
        while parent.setdefault(i, i) != i:
            i = parent[i]
        return i

    for i, t in enumerate(g.types):
        if t != "playerLocation" or (comb := _gate_and(c, i)) is None:
            continue
        for lk, _ in c.inc.get(comb, []):
            for other in _bounce_guard(c, lk.src):
                parent[root(i)] = root(other)
    groups = collections.defaultdict(list)
    for i in parent:
        groups[root(i)].append(i)
    return sorted(sorted(v) for v in groups.values())


def teleporter_routes(c: _Ctx, locators: list[int]) -> list[dict]:
    """How a teleporter pair sends the player, decoded from its wiring: a
    locator's ``teleport`` is a switch's ``output``, turned on by an
    and-combiner over a touch of a field pad, the guard against bouncing
    straight back, stored constants and the ``goal`` of both beam switches,
    each latched by a touch of its reset pad unless it starts on
    (``Teleporters_AlwaysON``).  So the field pad sends the player to the
    locator only once the reset pads in ``needs`` have been touched.  A
    beam switch is in its level's save list, so a touched reset pad stays
    latched on later visits.  Any other wiring raises :exc:`ValueError`
    naming it."""
    g = c.g
    routes = []
    for loc in locators:
        comb = _gate_and(c, loc)
        if comb is None:
            raise ValueError(f"teleporter {c.gid(loc)} ({c.name(loc)}): its teleport is not a switch "
                             f"turned on by an and-combiner")
        n, _ = combiner_header(g, comb)
        stored = g.attrs(comb)
        touch, needs = [], []
        for q in range(n):
            ins = c.into(comb, f"inputs[{q}]")
            if not ins:
                if stored[q] == 0.0:
                    raise ValueError(f"teleporter {c.gid(loc)}: and-input {q} is a stored 0")
                continue
            if len(ins) != 1:
                raise ValueError(f"teleporter {c.gid(loc)}: and-input {q} has {len(ins)} links")
            src, sp = ins[0][0].src, g.plug_name(ins[0][0].src, ins[0][0].src_plug)
            st = g.types[src]
            if st == "platform" and sp == "touch":
                touch.append(c.gid(src))
            elif st == "switch" and sp == "goal":
                if c.into(src, "turnOff") or c.into(src, "toggle") or g.attrs(src)[2] or g.attrs(src)[3]:
                    raise ValueError(f"teleporter {c.gid(loc)}: beam switch {c.name(src)} can turn off")
                if src not in c.saved:
                    raise ValueError(f"teleporter {c.gid(loc)}: beam switch {c.name(src)} is not saved")
                if g.attr_named(src, "goal") != 0.0:
                    continue   # the beam starts on
                pads = c.into(src, "turnOn")
                if len(pads) != 1 or g.types[pads[0][0].src] != "platform" \
                        or g.plug_name(pads[0][0].src, pads[0][0].src_plug) != "touch":
                    raise ValueError(f"teleporter {c.gid(loc)}: beam switch {c.name(src)} is not "
                                     f"turned on by one pad's touch")
                needs.append(c.gid(pads[0][0].src))
            elif not _bounce_guard(c, src):
                raise ValueError(f"teleporter {c.gid(loc)}: and-input {q} is {st} "
                                 f"{c.name(src)}.{sp}, which this decode doesn't know")
        if len(touch) != 1:
            raise ValueError(f"teleporter {c.gid(loc)}: {len(touch)} field pads, not one")
        routes.append({"to": c.gid(loc), "touch": touch[0], "needs": sorted(needs, key=_id_key)})
    return routes


def _id_key(gid: str) -> tuple[str, int, int]:
    f, g, r = gid.split("/")
    return f, int(g[1:]), int(r[1:])


# --------------------------------------------------------------------------- the extractor
class _Level:
    """One level XBR, read and parsed once."""

    def __init__(self, stem: str, data: bytes, schema: nodes.Schema):
        self.stem, self.data = stem, data
        self.toc = parse_toc(data)
        self.ctxs = [_Ctx(stem, gi, g) for gi, g in enumerate(nodes.graphs(data, schema))]
        self.cells = nodes.cells(data)


def extract_level(lv: _Level, combo_of: dict, key_codes: dict, char_ctxs: dict,
                  spots: dict, on_disc: set[str]) -> dict:
    """The generated data of one level (FORMAT §3)."""
    lvl, data, toc, ctxs, cells = lv.stem, lv.data, lv.toc, lv.ctxs, lv.cells
    path = f"gamedata/{lvl}.xbr"
    node_entries = [t for t in toc if t.tag == "node"]
    out = {"_meta": {"format": FORMAT, "generator": GENERATOR, "date": RULES_DATE,
                     "source": {"file": path, "size": len(data),
                                "sha256_12": hashlib.sha256(bytes(data)).hexdigest()[:12]}},
           "level": lvl, "kind": LEVEL_KIND.get(lvl, "realm"), "cells": cells, "graphs": [],
           "locations": [], "geodes": [], "barriers": [], "keylocks": [], "keylords": [],
           "obsidian_locks": [], "seals": [], "save_points": [], "exits": [], "spots": [],
           "teleporters": [], "bosses": [], "latches": [], "game_states": []}
    # graph metadata: the new-string budget is the zero padding after each node section
    ents = sorted(toc, key=lambda t: t.file_offset)
    for c in ctxs:
        ne = node_entries[c.gi]
        k = ents.index(ne)
        nxt = ents[k + 1].file_offset if k + 1 < len(ents) else len(data)
        out["graphs"].append({"g": c.gi, "toc_index": ne.index, "ndbg_toc_index": c.g.ndbg_index,
                              "records": len(c.g.recs), "links": sum(1 for _ in c.g.all_links()),
                              "saved_nodes": len(c.saved), "padding_after": nxt - (ne.file_offset + ne.size)})
    gsn = {}
    for c in ctxs:
        for i, t in enumerate(c.g.types):
            if t == "gameState":
                gsn[(c.gi, i)] = gamestate_vars(c.g, i)

    # ---------------------------------------------------------------- locations
    loc_by_rec = {}
    for c in ctxs:
        g = c.g
        for i, ro in enumerate(g.recs):
            if ro is None or g.types[i] != "critterGenerator":
                continue
            crit = g.pstr(ro, 0x1C) or ""
            cls, item = classify(crit)
            if cls is None:
                continue
            pts = g.list_at(i, 0x2C)[1]
            mg = g.attr_named(i, "maxGenerated")
            en = g.attr_named(i, "enable")
            yld = int(-mg * pts) if mg < 0 else (int(mg) if mg > 0 else None)
            if cls == "gem" and yld is not None and yld > 1:
                cls = "cluster"
            enable_in = c.into(i, "enable")
            sto, ln = g.str_target(i, 0x1C)
            p = g.parent(i)
            cell = struct.unpack_from("<H", g.s, ro + 0x34)[0]
            loc = {"id": c.gid(i), "name": c.name(i), "class": cls, "item": item, "template": crit,
                   "yield": yld, "unbounded": yld is None, "points": pts, "on_load": en != 0.0,
                   "enabled_by": [f"{c.gid(lk.src)} {c.name(lk.src)}.{g.plug_name(lk.src, lk.src_plug)}"
                                  for lk, _ in enable_in],
                   "dead": en == 0.0 and not enable_in, "saved": i in c.saved,
                   "cell": cells[cell] if cell < len(cells) else None, "parent": c.name(p) if p is not None else None,
                   "namespace": ns_of(g.names[i]),
                   "name_ref": {"field": g.file_offset + ro + 0x1C, "string": g.file_offset + sto, "length": ln},
                   "pool": lvl != "training_room" and not (en == 0.0 and not enable_in)}
            if lvl in GUARDIAN_SLOT and item == GUARDIAN_SLOT[lvl] and not loc["dead"]:
                loc["guardian_slot"] = True
            out["locations"].append(loc)
            loc_by_rec[(c.gi, i)] = loc
    if lvl in CHARACTER_SLOTS:
        gi, want = CHARACTER_SLOTS[lvl]
        cc = char_ctxs[gi]
        cg = cc.g
        for i, t in enumerate(cg.types):
            if t == "critterGenerator" and cg.pstr(cg.recs[i], 0x1C) == want:
                ro = cg.recs[i]
                sto, ln = cg.str_target(i, 0x1C)
                mg = cg.attr_named(i, "maxGenerated")
                pts = cg.list_at(i, 0x2C)[1]
                out["locations"].append({
                    "id": cc.gid(i), "name": cc.name(i), "class": "major", "item": want, "template": want,
                    "yield": int(-mg * pts) if mg < 0 else int(mg), "unbounded": False, "points": pts,
                    "on_load": False, "dead": False, "saved": i in cc.saved, "cell": None, "parent": None,
                    "namespace": None,
                    "enabled_by": [f"{cc.gid(lk.src)} {cc.name(lk.src)}.{cg.plug_name(lk.src, lk.src_plug)}"
                                   for lk, _ in cc.into(i, "enable")],
                    "name_ref": {"field": cg.file_offset + ro + 0x1C, "string": cg.file_offset + sto, "length": ln},
                    "pool": True, "guardian_slot": True,
                    "note": f"spawned by the boss's character graph (characters.xbr graph {gi}); the {lvl} level "
                            f"generator for {want} is dead (thresholds/disc_chains.txt)"})

    # ---------------------------------------------------------------- barriers and geodes (the census grouping)
    for c in ctxs:
        g = c.g
        sizes = g.record_sizes()

        groups = collections.defaultdict(list)
        for i, ro in enumerate(g.recs):
            if ro is None or g.types[i] != "platform" or sizes[i] < 64:
                continue
            st, n = g.list_at(i, 0x38)
            if not n:
                continue
            fc = g.s[st:st + 4].rstrip(b"\x00").decode("ascii", "replace")
            if fc in ("none", "") or fc not in combo_of and fc not in ("elem", "norm"):
                continue
            groups[top_group(g, i) or g.names[i]].append((i, fc))
        gen_group = {i: top_group(g, i) for (gi, i) in loc_by_rec if gi == c.gi}

        for key, members in sorted(groups.items(), key=lambda kv: min(i for i, _ in kv[1])):
            recs = sorted(i for i, _ in members)
            fcs = collections.Counter(fc for _, fc in members)
            fc = fcs.most_common(1)[0][0]
            levels, targets = set(), []
            for i in recs:
                for dst, plug, L in magic_level(c, i):
                    targets.append((dst, plug, L))
                    if g.types[dst] in ("switch", "critterGenerator") and L is not None:
                        levels.add(L)
            sw = sorted({dst for dst, _, _ in targets if g.types[dst] == "switch"})
            if not targets:
                persist = "unknown"
            elif sw and all(g.attrs(s)[2] != 0.0 for s in sw):
                persist = "timed"
            elif sw and all(s in c.saved for s in sw):
                persist = "permanent"
            elif sw:
                persist = "level_reset" if not any(g.attrs(s)[2] != 0.0 for s in sw) else "mixed"
            else:
                persist = "permanent" if all(dst in c.saved for dst, _, _ in targets) else "level_reset"
            lvl_min = min(levels) if levels else None
            combo = combo_of.get(fc)
            m = GEODE.search(key)
            kind = ("geode" if m else
                    "firewall" if re.search(r"firewall|flamespout", key, re.I) else
                    "iceblock" if re.search(r"ice ?block", key, re.I) else
                    "acidblock" if re.search(r"acid", key, re.I) else
                    "crystal" if re.search(r"crystal", key, re.I) else
                    "trap" if re.search(r"trap", key, re.I) else "other")
            ent = {"id": c.gid(recs[0]), "name": key, "kind": kind, "damage": fc,
                   "damage_mix": dict(fcs) if len(fcs) > 1 else None,
                   "elements": combo, "level": lvl_min, "levels_seen": sorted(levels),
                   "persist": persist, "shapes": [c.gid(i) for i in recs],
                   "switches": [c.gid(s) for s in sw],
                   "requires": requires_for_damage(combo, lvl_min)}
            contained = sorted(i for i, gk in gen_group.items() if gk == key)
            enabled = sorted({lk.dst for i in recs for lk in g.links(i)
                              if g.plug_name(i, lk.src_plug) == "magic" and (c.gi, lk.dst) in loc_by_rec})
            if m:
                ent["variant"] = m.group(1).capitalize() + "Stone"
                locs = sorted(set(contained) | set(enabled))
                ent["locations"] = [c.gid(i) for i in locs]
                ent["contents"] = dict(collections.Counter(loc_by_rec[(c.gi, i)]["item"] for i in locs))
                for i in locs:
                    loc_by_rec[(c.gi, i)]["geode"] = ent["id"]
                out["geodes"].append(ent)
            else:
                ent["contains"] = [c.gid(i) for i in contained]
                cen = [_pivot(g, i) for i in recs]
                cc = tuple(sum(p[k] for p in cen) / len(cen) for k in range(3))
                near = []
                for (gi, i), loc in sorted(loc_by_rec.items()):
                    if gi != c.gi or loc["class"] == "consumable" or i in contained:
                        continue
                    if min(math.dist(cc, q) for q in _gen_points(g, i)) <= 4.0:
                        near.append(c.gid(i))
                ent["near_locations"] = near
                for i in contained:
                    loc_by_rec[(c.gi, i)]["inside_barrier"] = ent["id"]
                out["barriers"].append(ent)

    # ---------------------------------------------------------------- keylocks and keylords
    for c in ctxs:
        g = c.g
        for word in ("keylock", "keylordSystem"):
            groups = collections.defaultdict(list)
            for i, nm in enumerate(g.names):
                if g.recs[i] is not None:
                    ns = prefab_ns(nm, word)
                    if ns:
                        groups[ns].append(i)
            for ns, recs in sorted(groups.items()):
                if word == "keylock":
                    trig = [i for i in recs if g.types[i] == "platform"
                            and fourcc(struct.unpack_from("<I", g.s, g.recs[i] + 0x40)[0]) not in (None, "none", "open")]
                    tog = [i for i in recs if g.types[i] == "switch" and g.names[i].endswith("LockToggle")]
                    rs = set(recs)
                    ext_out = [lk for i in recs for lk in g.links(i) if lk.dst not in rs]
                    ent = {"namespace": ns, "records": len(recs),
                           "lock_toggle": c.gid(tog[0]) if tog else None,
                           "saved": bool(tog) and tog[0] in c.saved,
                           "drives": {k: len(v) for k, v in _downstream(g, ext_out).items()},
                           "drives_out": sorted({f"{g.names[lk.dst]}.{g.plug_name(lk.dst, lk.dst_plug)}"
                                                 for lk in ext_out})}
                    if trig:
                        fc = fourcc(struct.unpack_from("<I", g.s, g.recs[trig[0]] + 0x40)[0])
                        key = key_codes.get(fc)
                        ent.update(id=c.gid(trig[0]), coded=True, trigger=c.gid(trig[0]), key_fourcc=fc, key_type=key,
                                   consumes=f"key.{key[4:]}" if key else None,
                                   requires=f"key.{key[4:]}>=1" if key else None)
                    else:
                        src = sorted({prefab_ns(c.name(lk.src), "keylock") for i in tog for lk, _ in c.inc.get(i, [])}
                                     - {None, ns})
                        ent.update(id=c.gid(tog[0]) if tog else c.gid(recs[0]), coded=False, trigger=None,
                                   key_fourcc=None, key_type=None, consumes=None, requires=None, relay_of=src)
                    out["keylocks"].append(ent)
                else:
                    gens = {g.pstr(g.recs[i], 0x1C): i for i in recs if g.types[i] == "critterGenerator"}
                    lord, keyg = gens.get("keylord"), next((i for cr, i in gens.items() if cr and cr.startswith("key_")), None)
                    cage = next((i for i in recs if g.types[i] == "platform"
                                 and fourcc(struct.unpack_from("<I", g.s, g.recs[i] + 0x40)[0]) == "open"), None)
                    toggle2 = next((i for i in recs if g.names[i].endswith(":toggle2")), None)
                    ent = {"id": c.gid(lord) if lord is not None else c.gid(recs[0]), "namespace": ns,
                           "complete": lord is not None and keyg is not None,
                           "keylord": c.gid(lord) if lord is not None else None,
                           "key_location": c.gid(keyg) if keyg is not None else None,
                           "key_item": g.pstr(g.recs[keyg], 0x1C) if keyg is not None else None,
                           "cage": c.gid(cage) if cage is not None else None,
                           "latch_toggle": c.gid(toggle2) if toggle2 is not None else None,
                           "event": f"{lvl}.{ns}.killed"}
                    if keyg is not None and (c.gi, keyg) in loc_by_rec:
                        loc_by_rec[(c.gi, keyg)]["keylord"] = ent["id"]
                    out["keylords"].append(ent)

    # ---------------------------------------------------------------- town obsidian locks
    for c in ctxs:
        g = c.g
        for i, nm in enumerate(g.names):
            if nm != "temple:ObsidianCounter_gameState":
                continue
            locks = {}
            for k, lk in enumerate(g.links(i)):
                m = re.match(r"temple:templeObsidianLocks(\d*):public_(Locked|Open)Lock_andCombiner$", c.name(lk.dst))
                if not m:
                    continue
                cv = link_curve(g, i, k)
                n = int(m.group(1) or 0) + 1
                ent = locks.setdefault(n, {"namespace": f"temple:templeObsidianLocks{m.group(1)}"})
                if m.group(2) == "Open":
                    opens = [x for x in range(0, 101) if link_value(cv, float(x), lk.weight, lk.factor) != 0.0]
                    ent["threshold"] = min(opens) if opens else None
                    ent["open_combiner"] = c.gid(lk.dst)
            for n, ent in sorted(locks.items()):
                ns = ent["namespace"]
                tog = next((j for j, nm2 in enumerate(g.names) if nm2 == f"{ns}:Lock_toggle"), None)
                inside = sorted(j for (gi, j), loc in loc_by_rec.items() if gi == c.gi
                                and ((loc["namespace"] or "") == ns or (loc["namespace"] or "").startswith(ns + ":")))
                ent.update(id=ent["open_combiner"], lock=n, lock_toggle=c.gid(tog) if tog is not None else None,
                           saved=tog in c.saved if tog is not None else False,
                           locations=[c.gid(j) for j in inside], requires=f"obsidian>={ent['threshold']}")
                for j in inside:
                    loc_by_rec[(c.gi, j)]["obsidian_lock"] = ent["id"]
                out["obsidian_locks"].append(ent)

    # ---------------------------------------------------------------- seals
    for c in ctxs:
        g = c.g
        for i, nm in enumerate(g.names):
            if g.types[i] != "switch" or not (nm or "").endswith("Seal_toggle"):
                continue
            act = [lk.src for lk, _ in c.into(i, "turnOn")
                   if g.types[lk.src] == "combiner" and c.name(lk.src).endswith("SealActivate_andCombiner")]
            if not act:
                continue
            a = act[0]
            atoms, touch = [], []
            for lk, k in c.inc.get(a, []):
                s = lk.src
                if g.types[s] == "gameState":
                    var = gsn.get((c.gi, s), {}).get(lk.src_plug, "")
                    cond = nonzero_when(link_curve(g, s, k), lk.weight, lk.factor, var)
                    m = re.fullmatch(r">=(\d+)", cond)
                    atoms.append(f"{GS_COUNTER.get(var, var)}>={m.group(1)}" if m and var in GS_COUNTER else f"<{var} {cond}>")
                elif g.types[s] == "platform":
                    touch.append(f"{c.gid(s)} {c.name(s)}.{g.plug_name(s, lk.src_plug)}")
            sets = sorted({g.pstr(g.recs[lk.dst], 0x18) or c.name(lk.dst) for lk in g.links(i)
                           if g.types[lk.dst] == "latch"})
            opens = sorted({f"{c.name(lk.dst)}.{g.plug_name(lk.dst, lk.dst_plug)}" for lk in g.links(i)
                            if not POSITIONAL.search(g.plug_name(lk.dst, lk.dst_plug))})
            also = sorted({f"{c.name(lk.dst)}.{g.plug_name(lk.dst, lk.dst_plug)}" for lk in g.links(a)
                           if lk.dst != i})
            out["seals"].append({"id": c.gid(i), "name": c.name(i), "activate": c.gid(a),
                                 "requires": " & ".join(sorted(atoms)), "touch": touch,
                                 "saved": i in c.saved, "sets_globals": sets, "drives": opens,
                                 "activate_also_drives": also})

    # ---------------------------------------------------------------- save points, exits, spots, bosses, latches, gameStates
    for c in ctxs:
        g = c.g
        str_users = collections.Counter()
        for i, t in enumerate(g.types):
            if t == "levelSwitch":
                str_users[g.str_target(i, 0x20)[0]] += 1
        for i, ro in enumerate(g.recs):
            if ro is None:
                continue
            t = g.types[i]
            if t == "gameSaveControl":
                out["save_points"].append({"id": c.gid(i), "name": c.name(i), "save_id": g.pstr(ro, 0x1C),
                                           "saved": i in c.saved,
                                           "do_save": explain(c, gsn, i, "doSave") or None})
            elif t == "levelSwitch":
                dest, spot, movie = g.pstr(ro, 0x20), g.pstr(ro, 0x28), g.pstr(ro, 0x18)
                dl = dest.split("/")[-1] if dest and dest.startswith("levels/") else None
                if dl is not None and dl.lower() not in on_disc:
                    continue   # a level that isn't on the disc: f1's levelSwitch3 -> f7 (AZ-290)
                kind = ("ending" if dest == "return-to-shell" else "start" if dest == "start-playing" else
                        "teleport" if dl == lvl else "exit" if dl else "other")
                known = dl in spots
                arrival, arrival_by = resolve_arrival(spots[dl], spot) if known else (None, None)
                gate = explain(c, gsn, i, "activate")
                out["exits"].append({"id": c.gid(i), "name": c.name(i), "kind": kind, "dest": dest, "dest_level": dl,
                                     "spot": spot, "movie": movie, "arrival": arrival, "arrival_by": arrival_by,
                                     "arrival_graph_known": (spots[dl]["graphs"] == 1) if known else None,
                                     "dest_string_shared_by": str_users[g.str_target(i, 0x20)[0]],
                                     "live": bool(gate) and bool(SOURCE_ATOM.search(gate)), "gate_hint": gate or None,
                                     "disc_teleport": DISC_TELEPORT.get((lvl, c.name(i)))})
            elif t == "playerLocation":
                out["spots"].append({"id": c.gid(i), "name": c.name(i),
                                     "teleport_gate": explain(c, gsn, i, "teleport") or None})
            elif t == "critterGenerator" and (g.pstr(ro, 0x1C) or "") in BOSSES:
                out["bosses"].append({"id": c.gid(i), "name": c.name(i), "critter": g.pstr(ro, 0x1C),
                                      "saved": i in c.saved, "on_load": g.attr_named(i, "enable") != 0.0,
                                      "enabled_by": explain(c, gsn, i, "enable") or None,
                                      "num_dead_drives": sorted({f"{c.name(lk.dst)}.{g.plug_name(lk.dst, lk.dst_plug)}"
                                                                 for lk in g.links(i) if g.plug_name(i, lk.src_plug) == "numDead"}),
                                      "event": f"{lvl}.{g.pstr(ro, 0x1C)}.killed"})
            elif t == "latch":
                out["latches"].append({"id": c.gid(i), "name": c.name(i), "global": g.pstr(ro, 0x18) or None,
                                       "saved": i in c.saved,
                                       "update": explain(c, gsn, i, "update") or None,
                                       "input": explain(c, gsn, i, "input") or None})
            elif t == "gameState":
                links = []
                for k, lk in enumerate(g.links(i)):
                    plug = g.plug_name(lk.dst, lk.dst_plug)
                    if POSITIONAL.search(plug):
                        continue
                    var = gsn.get((c.gi, i), {}).get(lk.src_plug, f"value{lk.src_plug}")
                    try:
                        cond = nonzero_when(link_curve(g, i, k), lk.weight, lk.factor, var)
                    except ValueError:
                        cond = "curve"
                    links.append({"var": var, "when": cond, "to": f"{c.name(lk.dst)}.{plug}"})
                out["game_states"].append({"id": c.gid(i), "name": c.name(i),
                                           "vars": sorted(set(gsn.get((c.gi, i), {}).values())), "links": links})
        for locs in teleporter_pairs(c):
            out["teleporters"].append({"id": c.gid(locs[0]), "namespace": ns_of(g.names[locs[0]]),
                                       "locators": [c.gid(i) for i in locs], "routes": teleporter_routes(c, locs)})
    # gated_by: the generated objects a location's spawn depends on
    boss_by_rec = {b["id"]: b for b in out["bosses"]}
    for loc in out["locations"]:
        gates = [loc[k] for k in ("geode", "keylord", "obsidian_lock") if loc.get(k)]
        for src in loc["enabled_by"]:
            sid = src.split(" ", 1)[0]
            if sid in boss_by_rec and src.endswith(".numDead"):
                gates.append(sid)
        if loc["id"].startswith("characters/"):
            gates += [b["id"] for b in out["bosses"] if b["critter"] == SLOT_BOSS[lvl]]
        loc["gated_by"] = sorted(set(gates))
    for k in ("locations", "exits", "spots", "save_points", "bosses", "latches", "game_states", "keylocks", "keylords",
              "seals", "obsidian_locks", "teleporters"):
        out[k].sort(key=lambda x: _id_key(x["id"]))
    cnt = collections.Counter(loc["class"] for loc in out["locations"] if loc["pool"])
    out["counts"] = {"locations_in_pool": dict(sorted(cnt.items())),
                     "locations_not_in_pool": sum(1 for loc in out["locations"] if not loc["pool"]),
                     **{k: len(out[k]) for k in ("geodes", "barriers", "keylocks", "keylords", "obsidian_locks", "seals",
                                                 "save_points", "exits", "spots", "teleporters", "bosses", "latches",
                                                 "game_states")}}
    return out

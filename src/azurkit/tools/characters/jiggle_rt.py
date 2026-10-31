"""Real-time jiggle (Step 2.156; D443, D444, D445; X41,
``player_model/jiggle.c``): a worn body's jiggle bones (W29's, or any
named bone a recipe gives a ``spring``) swing on damped springs the game
steps every pose from the player's own drawn motion, so every step,
landing, hit, spin and stop moves them as it happens (no keys baked).

- **The drive.** Each spring row has one or two probes (its ``centre``
  plus and minus its ``sides`` along the model's x at bind), carried by
  the bone as the engine poses it and into the world by the game's own
  drawn matrix (``critter_model_matrix`` 0x42200, its 3x3 times the
  drawn scale +0x188): a probe's world path is exactly the drawn
  body's, its aligned-node term (a climb-over's 2.6 m) included.  Its
  velocity over a pose tick is filtered (``give``, a first-order lag)
  and differenced into an acceleration, softly capped at ``accel``
  (``a / sqrt(1 + (|a| / accel)^2)``).
- **The spring.** Per probe and world axis a mass on a damped spring of
  ``freq`` (or ``stiffness`` over ``mass``) and damping ratio
  ``damping``, forced by gravity (``gravity`` x 9.8 m/s^2, ``swim[0]``
  of it in water) less the acceleration, stepped exactly by the
  transition (Phi, gamma) of one :data:`H` substep (the build computes
  both in float64 for land and for water, :func:`step_matrix`; the shim
  has no exponential).  The offset shown is the mass's place less its
  rest sag (``g / w^2`` along the body's bind-down, turned with it):
  standing still it is 0, in the air the forms float, bent over they
  hang.
- **The shape.** The offset turned into the bone's bind axes (side,
  forward, up), weighted per axis (``weights``) and times ``gain`` and
  the strength slider, passes a soft ellipsoid limit (``travel``, per
  axis, linear to :data:`KNEE` of it, then easing to it); two probes'
  difference over their span gives a roll (about forward) and a yaw
  (about up), each softly limited at ``turn``.  The bone's matrix is
  post-multiplied by a rigid move in its bind frame: the twist about
  the centre, a swing about the ``pivot`` taking ``rot_share`` of the
  offset as a rotation, and the rest as a translation, so the centre
  moves exactly by the offset.  ``gain`` scales only the springs' motion
  (the mass's place less its world rest, ``g / w^2`` straight down): the
  hang, where the bone's tilt leaves its rest sag, shows at 1, so a
  fast tilt (a roll, a hand spin, a death) never throws the form
  (tuning sitting 1's pop).
- **Squash and stretch** (D481): before that move the form is scaled
  about its centre in its bind axes by ``e^(eps_i - (eps_j + eps_k) /
  2)``, ``eps_i`` = ``squash[i]`` x the offset along axis i over its
  travel (softly limited at 1): its volume kept, it settles with the
  swing; booblord's squashes along up as the form drops onto a landing
  and stretches as it lifts, and squashes along forward as it swings
  out on a stop.
- **Chains** (D485): a row whose bone descends from another row's
  (``chain``: a ponytail's links, each its own spring) is built by the
  game from that row's written world, so its probes carry the parent's
  simulated swing; its drive takes that swing in full and only the
  clip's own motion at the ``pace``.  ``springs`` rows (a recipe's
  ``jiggle.springs``) name any bone of the body as it is, its own skin
  and children, no reskin: a chain's links.
- **A run's start kicks** (Step 2.156b, D518, AZ-678): from standing,
  a turn into a run (a pivot, or the arc of her first strides) throws
  the forms sideways, and that level drive takes the soft cap's share
  from the up one, so a resonant spring's stride bounce started at or
  under the bake's for 1-1.5 s.  Once she moves off (:data:`START` on
  the ground, state 0) after standing (under :data:`REST`), for
  ``kick_time`` s while she runs (:data:`RUN_ON`) each row's level drive
  (sideways and fore and aft) is held to ``1 - kick_hold x e`` of itself
  (none below 0; before the cap) and its up drive, her first footfalls'
  push, raised to ``1 + kick x e`` (after the cap), ``e`` falling
  linearly from 1 to 0 over the window; a stop (under :data:`START`), a
  jump, a hit or any other state ends it, any state but the ground's
  disarms it until she stands again (so a standing jump steered forward
  lands running with none) and a walk has none, so landings, stops and
  walks are as before.
- **A landing's impact** (Step 2.174, D584, D619): the soft cap holds a
  landing's push near one size whatever the fall, and a hard landing's
  crouch (state :data:`HARD_STATE`, a 6 m fall's 13 ticks), sinking her
  again at up to 5.6 m/s 2-4 ticks after the stop and lifting her
  3 m/s 8-11 ticks on, cut its dive and braked its rebound (xemu: the
  bust's 80 and 85 mm dives from 1 and 3 m, 46 from 6 m).  So a row
  with an ``impact`` keys a landing's up push on the speed it met the
  ground at: the step a probe falling faster than :data:`IMPACT_FALL`
  (its filtered velocity) is first pushed up while she isn't in the air
  (:data:`AIR_STATE`) but was within :data:`LAND_TIME` (a clip's own
  drop while she stands, a death's or a victory's, opens none), it is
  owed ``impact`` x that speed as a push along the bone's up as drawn
  (its bind up, turned with her: the crouch bends her forward, and a
  world-up push there went into the forward axis's short travel), past
  the cap, spread evenly over :data:`LAND_TIME` in place of its own up
  drive, which stays held for :data:`LAND_TIME` and, a landing begun in
  the hard landing, through that crouch; so a longer fall bounces the
  forms further, held only by the travel's soft limit and the state
  stop.
- **Walls** (Step 2.169b, D536: a cloth chain, booblord's sash and
  tabard): a row's ``wall`` is a unit ``axis`` in the bone's bind axes,
  toward her (the panel's face after its clip's hang), and a ``stop`` m
  as drawn.  The allowance is the stop less how far the row's parents'
  swing already carries its probe in along the axis off the clip's pose
  (the probe as built from the parent row's written world less the probe
  as the clip poses it), so the stops don't add up down a chain; where
  the raw offset passes it, that part comes off the mass and its inward
  speed bounces with :data:`RESTITUTION`, and after the soft limit the
  shown offset is held to it.  No tip comes nearer her than its stop off
  the clip's pose, a link its parent swung in is turned back out, and
  outward and sideways stay free; at a gain of 0 no wall acts.
- **Discontinuities kick nothing.** A tick whose probe moved more than
  :data:`TELEPORT` m off the physics' own velocity (a place), or whose
  glide mode changed, keeps the filtered velocity and takes no
  acceleration; a gap over :data:`GAP` s rings the springs on
  :data:`GAP_STEPS` substeps under gravity alone; a new anim object,
  player or controller, the clock going back or anything non-finite
  resets (the bone drawn as the game poses it); a clip change keeps the
  springs.  The state stop at :data:`BOUND` x the largest travel bounces
  with restitution :data:`RESTITUTION`, so any finite slider stays
  finite.

:func:`table` packs the rows into X41's table (:data:`TABLE_SIZE`
bytes), :class:`Twin` is the shim's arithmetic in Python float64 (the
L2 test's oracle and the preview's engine) and :func:`preview` drives it
over a built body's clips at the rates the game plays them and over
physics scenarios (``azurik-mod model jiggle``).  Arithmetic is plain
floats with ``sqrt`` the only function, so a build writes the same
bytes on every machine.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field, replace
from azurkit.core import fdlibm

G = 9.8
"""m/s^2, the world's gravity (``0x1980A8``)."""
H = 1.0 / 120.0
"""The spring's substep, s: 4 a 30 Hz pose, 2 at fps_unlock's 60."""
SUBSTEP_EDGE = 0.999999
"""A substep is due once the accumulated time passes this share of :data:`H`."""
MAX_SUBSTEPS = 32
FADE = 0.25
"""s: a clip change's crossfade (anim+0x14, ``0x197564``)."""
GAP = 0.25
"""A pose tick longer than this (s: a pause, a hitch) rings the springs
free instead of driving them."""
GAP_STEPS = 30
"""How many substeps a gap rings for (0.25 s)."""
TELEPORT = 1.0
"""m: a probe that moved this far off the physics' velocity in one tick
was placed, not moved."""
KNEE = 0.6
"""The soft limits are linear to this share of their stop."""
BOUND = 3.0
"""The state stop: the offset's raw radius at most this many times the
largest travel."""
RESTITUTION = 0.3
"""How much of its outward speed a mass keeps off the state stop."""
IMPACT_FALL = 3.0
"""m/s: a probe falling faster than this (about a 0.5 m drop) when it is
first pushed up off the air lands with its row's ``impact``."""
LAND_TIME = 0.15
"""s: a landing's push is spread evenly over this long, the probe's own
up drive held meanwhile (and through a hard landing it began in)."""
AIR_STATE = 2
"""PlayerControl +0x94 in the air: no landing starts there, and none
starts later than :data:`LAND_TIME` after it."""
HARD_STATE = 0x100
"""PlayerControl +0x94 in a hard landing's crouch (a long fall's: 6 m's,
not 3 m's; also an attack's): a landing begun in it holds through it."""
SWIM_STATE = 6
"""PlayerControl +0x94 while swimming: the water coefficients."""
HIT_STATE = 0x102
"""PlayerControl +0x94 in a hit reaction (0x8D682, on land or in the water):
it keeps the coefficients of the state it was hit in."""
MAX_ROWS = 32
MAX_BONES = 256
MAGIC = b"JGL1"
HEADER_SIZE = 288
ROW_SIZE = 400
TABLE_SIZE = HEADER_SIZE + MAX_ROWS * ROW_SIZE
"""X41's table: a header (:data:`MAGIC`, rows, the body's bone count,
flags, f64 h, f32 stiffness and drawn scale recorded, u8 map[256] bone
-> row + 1) and :data:`MAX_ROWS` rows of :data:`ROW_SIZE` bytes
(``jiggle.c``'s ``struct row``)."""
SHOWN_SIZE = 48
"""A row's shown words (``jiggle.c``'s ``struct shown``): the offset (mm
as drawn: side, forward, up), roll, yaw, the raw radius (f32 each), the
clock (f64) and the squash's three scales (f32), padded."""
TWO_PROBES, RESTS = 1, 2
"""A row's flags: two probes; its coefficients aren't finite, so its
bone is drawn as the game poses it."""

REST = 1.0
"""m/s on the ground (state 0): standing, so the next move off starts a
kick (a stop takes 7.0 to 0.46 in two ticks)."""
START = 2.0
"""m/s on the ground: moving off (a run's first tick 3.27, while a turn
into it still swings her round): the kick's clock starts; under it, the
kick ends."""
RUN_ON = 5.0
"""m/s on the ground: running (her run 7.0, a walk at most 4.9): only
then is the up drive raised."""

SPRING_KEYS = (("damping", "travel"),
               ("freq", "stiffness", "mass", "weights", "gain", "gravity", "turn", "rot_share", "sides", "centre",
                "pivot", "give", "accel", "swim", "pace", "squash", "kick", "kick_hold", "kick_time", "impact",
                "wall"))
"""A recipe's ``spring`` keys: required, then optional."""

Vec = tuple[float, float, float]


@dataclass(frozen=True)
class Spring:
    """A jiggle bone's real-time spring (a recipe row's ``spring``):
    ``freq`` Hz, or ``stiffness`` N/m over ``mass`` kg (exactly one form;
    ``mass`` beside ``freq`` is informational: it cancels under a moving
    base); ``damping`` the ratio zeta; ``travel`` (side, forward, up) m
    as drawn; ``weights`` per axis; ``gain`` on the offset; ``gravity``
    its share; ``turn`` the roll and yaw's stop, rad; ``rot_share`` the
    offset's share taken as a swing about ``pivot``; ``sides`` the
    probes' half-span (model units; ``None``: W29's, 0: one probe);
    ``centre`` (model units at bind; ``None``: the bone's bind origin);
    ``pivot`` relative to the centre (model units) or ``"origin"`` (the
    bone's bind origin); ``give`` s, the velocity filter's time
    constant (0: none); ``accel`` m/s^2, the soft cap (0: none);
    ``swim`` (gravity share, damping factor) in water; ``pace`` how
    a clip played faster than it was made drives them (:func:`pace_factor`:
    its pose's own motion times rate ** -pace, the body's motion in the
    world in full; 0: all in full); ``squash`` (side, forward, up) the
    form's strain along each bind axis at its full travel (signed: a
    positive one stretches the form as it moves that way, D481; its
    volume kept); ``kick`` the up drive's extra share and ``kick_hold``
    the level drive's share held back for ``kick_time`` s from a run's
    start, tapering to 0 (Step 2.156b, D518; 0: none); ``impact`` a
    landing's up push per m/s of the speed it met the ground at (Step
    2.174, D619; 0: none); ``wall`` (axis x, y, z, stop) a unit axis in
    the bone's bind axes toward her and the stop off the clip's pose along
    it, m as drawn (Step 2.169b; ``None``: none)."""

    damping: float
    travel: Vec
    freq: float | None = None
    stiffness: float | None = None
    mass: float | None = None
    weights: Vec = (1.0, 1.0, 1.0)
    gain: float = 1.0
    gravity: float = 1.0
    turn: float = 0.0
    rot_share: float = 0.0
    sides: float | None = None
    centre: Vec | None = None
    pivot: Vec | str = (0.0, 0.0, 0.0)
    give: float = 0.0
    accel: float = 0.0
    swim: tuple[float, float] = (1.0, 1.0)
    pace: float = 0.0
    squash: Vec = (0.0, 0.0, 0.0)
    kick: float = 0.0
    kick_hold: float = 0.0
    kick_time: float = 0.0
    impact: float = 0.0
    wall: tuple[float, float, float, float] | None = None


def _finite(where: str, value) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{where}: {value!r} is not a finite number")
    return float(value)


def _vec(where: str, value, n: int = 3) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != n:
        raise ValueError(f"{where}: {value!r} is not a list of {n} numbers")
    return tuple(_finite(f"{where}[{i}]", x) for i, x in enumerate(value))


def _wall(where: str, doc) -> tuple[float, float, float, float]:
    """A spring's ``wall``, ``{"axis": [x, y, z], "stop": m}``: any finite
    axis normalized and any finite stop (D23: a negative one holds the tip
    that far out); refused by name only where the axis is the zero vector
    (no direction) or a number isn't finite."""
    if not isinstance(doc, dict) or set(doc) != {"axis", "stop"}:
        raise ValueError(f"{where}: {doc!r} is not {{\"axis\": [x, y, z], \"stop\": m}}")
    axis = _vec(f"{where}.axis", doc["axis"])
    big = max(map(abs, axis))
    if not big > 0.0:
        raise ValueError(f"{where}.axis: {doc['axis']!r} has no direction")
    axis = tuple(a / big for a in axis)  # scaled first, so hypot can't overflow
    n = math.hypot(*axis)
    stop = _finite(f"{where}.stop", doc["stop"])
    return (axis[0] / n, axis[1] / n, axis[2] / n, stop)


def parse_spring(where: str, doc) -> Spring:
    """A recipe row's ``spring`` (:class:`Spring`): any finite number is
    taken (D23); NaN or inf, an unknown or missing key, both or neither
    of ``freq`` and ``stiffness``, ``stiffness`` without ``mass`` or a
    ``wall`` that isn't one (:func:`_wall`) is refused by name (D45)."""
    if not isinstance(doc, dict):
        raise ValueError(f"{where}: {doc!r} is not an object")
    need, maybe = SPRING_KEYS
    for k in doc:
        if k not in need + maybe:
            raise ValueError(f"{where}: unknown key {k!r} (one of {', '.join(need + maybe)})")
    for k in need:
        if k not in doc:
            raise ValueError(f"{where}: missing {k!r}")
    if ("freq" in doc) == ("stiffness" in doc):
        raise ValueError(f"{where}: give freq (Hz) or stiffness (N/m) with mass (kg), exactly one")
    if "stiffness" in doc and "mass" not in doc:
        raise ValueError(f"{where}: stiffness needs a mass (kg)")
    travel = doc["travel"]
    travel = ((_finite(f"{where}.travel", travel),) * 3 if not isinstance(travel, list)
              else _vec(f"{where}.travel", travel))
    pivot = doc.get("pivot", [0.0, 0.0, 0.0])
    if pivot != "origin":
        pivot = _vec(f"{where}.pivot", pivot)
    sides = doc.get("sides", "auto")
    centre = doc.get("centre", "auto")
    return Spring(
        damping=_finite(f"{where}.damping", doc["damping"]), travel=travel,
        freq=_finite(f"{where}.freq", doc["freq"]) if "freq" in doc else None,
        stiffness=_finite(f"{where}.stiffness", doc["stiffness"]) if "stiffness" in doc else None,
        mass=_finite(f"{where}.mass", doc["mass"]) if "mass" in doc else None,
        weights=_vec(f"{where}.weights", doc["weights"]) if "weights" in doc else (1.0, 1.0, 1.0),
        gain=_finite(f"{where}.gain", doc.get("gain", 1.0)),
        gravity=_finite(f"{where}.gravity", doc.get("gravity", 1.0)),
        turn=_finite(f"{where}.turn", doc.get("turn", 0.0)),
        rot_share=_finite(f"{where}.rot_share", doc.get("rot_share", 0.0)),
        sides=None if sides == "auto" else _finite(f"{where}.sides", sides),
        centre=None if centre == "auto" else _vec(f"{where}.centre", centre),
        pivot=pivot,
        give=_finite(f"{where}.give", doc.get("give", 0.0)),
        accel=_finite(f"{where}.accel", doc.get("accel", 0.0)),
        swim=_vec(f"{where}.swim", doc["swim"], 2) if "swim" in doc else (1.0, 1.0),
        pace=_finite(f"{where}.pace", doc.get("pace", 0.0)),
        squash=_vec(f"{where}.squash", doc["squash"]) if "squash" in doc else (0.0, 0.0, 0.0),
        kick=_finite(f"{where}.kick", doc.get("kick", 0.0)),
        kick_hold=_finite(f"{where}.kick_hold", doc.get("kick_hold", 0.0)),
        kick_time=_finite(f"{where}.kick_time", doc.get("kick_time", 0.0)),
        impact=_finite(f"{where}.impact", doc.get("impact", 0.0)),
        wall=_wall(f"{where}.wall", doc["wall"]) if "wall" in doc else None)


def spring_json(spring: Spring) -> dict:
    """``spring`` as a recipe's ``spring`` object (the preview's ``--set`` prints it)."""
    out: dict = {}
    if spring.freq is not None:
        out["freq"] = spring.freq
    else:
        out["stiffness"] = spring.stiffness
    if spring.mass is not None:
        out["mass"] = spring.mass
    out |= {"damping": spring.damping, "travel": list(spring.travel), "weights": list(spring.weights),
            "gain": spring.gain, "gravity": spring.gravity, "turn": spring.turn, "rot_share": spring.rot_share,
            "sides": "auto" if spring.sides is None else spring.sides,
            "centre": "auto" if spring.centre is None else list(spring.centre),
            "pivot": spring.pivot if spring.pivot == "origin" else list(spring.pivot),
            "give": spring.give, "accel": spring.accel, "swim": list(spring.swim), "pace": spring.pace,
            "squash": list(spring.squash), "kick": spring.kick, "kick_hold": spring.kick_hold,
            "kick_time": spring.kick_time, "impact": spring.impact}
    if spring.wall is not None:
        out["wall"] = {"axis": list(spring.wall[:3]), "stop": spring.wall[3]}
    return out


# --------------------------------------------------------------------------- the coefficients
def _exp(x: float) -> float:
    """e^x by scaling and squaring (plain arithmetic: the same bits on every machine)."""
    s = 0
    while abs(x) > 0.5 and s < 2000:
        x *= 0.5
        s += 1
    e = 1.0
    for n in range(16, 0, -1):   # Horner: 1 + x (1 + x/2 (1 + ... (1 + x/16)))
        e = 1.0 + x / n * e
    for _ in range(s):
        e *= e
    return e


LN2 = 0.6931471805599453
PACE_LIMIT = 700.0
"""The pace's exponent is held to +-this (e^700 is near float64's top)."""


def _ln(x: float) -> float:
    """ln x for x > 0 by halving to [0.75, 1.5] and atanh's series (plain
    arithmetic, as ``jiggle.c``'s)."""
    k = 0
    while x > 1.5 and k < 1100:
        x *= 0.5
        k += 1
    while x < 0.75 and k > -1100:
        x *= 2.0
        k -= 1
    z = (x - 1.0) / (x + 1.0)
    z2, term, total = z * z, z, 0.0
    for n in range(20):
        total += term / (2 * n + 1)
        term *= z2
    return 2.0 * total + k * LN2


def pace_factor(rate: float, pace: float) -> float:
    """How much of a pose's own motion drives the springs on a clip played
    at ``rate`` clip seconds a second: ``rate ** -pace`` above 1, else 1
    (Step 2.156: the game plays a clip faster to cover ground or time a
    move, which throws the forms no harder; AZ-648)."""
    if not (pace != 0.0 and rate > 1.0):
        return 1.0
    x = -pace * _ln(rate)
    return _exp(max(-PACE_LIMIT, min(PACE_LIMIT, x)))


def step_matrix(w2: float, beta: float, h: float) -> tuple[tuple[float, ...], tuple[float, float]]:
    """The exact step of ``u'' = -w2 u - beta u' + F`` over ``h`` with F
    constant: exp(h [[0, 1, 0], [-w2, -beta, 1], [0, 0, 0]]) by scaling
    and squaring, as Phi (a, b, c, d: u := a u + b v, v := c u + d v)
    and gamma (u += g0 F, v += g1 F)."""
    a = [[0.0, h, 0.0], [-w2 * h, -beta * h, h], [0.0, 0.0, 0.0]]
    norm = max(sum(abs(c) for c in r) for r in a)
    s = 0
    while norm > 0.5 and s < 2000:
        norm *= 0.5
        s += 1
    scale = math.ldexp(1.0, -s)
    b = [[c * scale for c in r] for r in a]

    def mm(x, y):
        return [[sum(x[i][k] * y[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    e = [[float(i == j) for j in range(3)] for i in range(3)]
    t = [[float(i == j) for j in range(3)] for i in range(3)]
    for n in range(1, 14):
        t = [[c / n for c in r] for r in mm(t, b)]
        e = [[e[i][j] + t[i][j] for j in range(3)] for i in range(3)]
    for _ in range(s):
        e = mm(e, e)
    return (e[0][0], e[0][1], e[1][0], e[1][1]), (e[0][2], e[1][2])


@dataclass(frozen=True)
class Coeffs:
    """A row's coefficients at a stiffness slider kappa (``w^2 = w0^2
    kappa``, ``beta = beta0 sqrt|kappa|``: the frequency x sqrt(kappa)
    at the same damping ratio): land and water transitions, gravity, the
    rest sag (0 where ``w^2 <= 0``) and the velocity filter's share a
    substep; ``rests`` when any isn't finite (its bone drawn as the game
    poses it)."""

    phi_land: tuple[float, ...]
    gamma_land: tuple[float, float]
    phi_swim: tuple[float, ...]
    gamma_swim: tuple[float, float]
    alpha: float
    g_land: float
    g_swim: float
    sag_land: float
    sag_swim: float
    w2: float
    rests: bool


def coefficients(spring: Spring, kappa: float = 1.0, h: float = H) -> Coeffs:
    """:class:`Coeffs` for ``spring`` at stiffness slider ``kappa``."""
    if spring.freq is not None:
        w0 = 2.0 * math.pi * spring.freq
        w02 = w0 * w0
    else:
        w02 = spring.stiffness / spring.mass if spring.mass != 0.0 else math.inf
    w2 = w02 * kappa
    beta = 2.0 * spring.damping * math.sqrt(abs(w02)) * math.sqrt(abs(kappa))
    phi_land, gamma_land = step_matrix(w2, beta, h)
    phi_swim, gamma_swim = step_matrix(w2, beta * spring.swim[1], h)
    alpha = 1.0 - _exp(-h / spring.give) if spring.give > 0.0 else 1.0
    g_land = G * spring.gravity
    g_swim = g_land * spring.swim[0]
    sag_land = g_land / w2 if w2 > 0.0 else 0.0
    sag_swim = g_swim / w2 if w2 > 0.0 else 0.0
    values = (*phi_land, *gamma_land, *phi_swim, *gamma_swim, alpha, g_land, g_swim, sag_land, sag_swim, w2, beta)
    return Coeffs(phi_land, gamma_land, phi_swim, gamma_swim, alpha, g_land, g_swim, sag_land, sag_swim, w2,
                  not all(math.isfinite(x) for x in values))


# --------------------------------------------------------------------------- the table
@dataclass(frozen=True)
class Row:
    """A spring row as the build packs it: its role, bone and parent
    indices, the :class:`Spring`, its coefficients, its probes' centre
    and half-span and its pivot (model units, bind), its inverse bind
    and bind world (16 floats each, D3D rows) and the row its bone
    descends from (``chain``: its index in the table, -1 none)."""

    role: str
    bone: int
    parent: int
    spring: Spring
    coeffs: Coeffs
    centre: Vec
    sides: float
    pivot: Vec
    ib: tuple[float, ...]
    wbind: tuple[float, ...]
    chain: int = -1

    @property
    def flags(self) -> int:
        return (TWO_PROBES if self.sides != 0.0 else 0) | (RESTS if self.coeffs.rests else 0)


def _inverse4(m) -> tuple[float, ...] | None:
    """The inverse of an affine D3D-row matrix (its last column 0, 0, 0, 1);
    ``None`` when it has none."""
    a = [[m[4 * r + c] for c in range(3)] for r in range(3)]
    inv = _inverse3(a)
    if inv is None:
        return None
    t = [m[12], m[13], m[14]]
    ti = [-sum(t[k] * inv[k][j] for k in range(3)) for j in range(3)]
    return (inv[0][0], inv[0][1], inv[0][2], 0.0, inv[1][0], inv[1][1], inv[1][2], 0.0,
            inv[2][0], inv[2][1], inv[2][2], 0.0, ti[0], ti[1], ti[2], 1.0)


def _inverse3(a):
    det = (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
           + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    if det == 0.0 or not math.isfinite(det):
        return None
    adj = [[a[1][1] * a[2][2] - a[1][2] * a[2][1], a[0][2] * a[2][1] - a[0][1] * a[2][2],
            a[0][1] * a[1][2] - a[0][2] * a[1][1]],
           [a[1][2] * a[2][0] - a[1][0] * a[2][2], a[0][0] * a[2][2] - a[0][2] * a[2][0],
            a[0][2] * a[1][0] - a[0][0] * a[1][2]],
           [a[1][0] * a[2][1] - a[1][1] * a[2][0], a[0][1] * a[2][0] - a[0][0] * a[2][1],
            a[0][0] * a[1][1] - a[0][1] * a[1][0]]]
    return [[adj[i][j] / det for j in range(3)] for i in range(3)]


def spring_places(names, parents, binds, bones) -> list:
    """A recipe's ``jiggle.springs`` (``bones``: each a
    :class:`~azurik_mod.assets.jiggle.Bone` with a ``spring`` and no
    shape) placed on the built body as it is (D485: any bone, its own
    skin and children, no W29 reskin), each a
    :class:`~azurik_mod.assets.jiggle.Placed`: its index and parent's, its
    centre (``"auto"``: its one child's bind origin, the link's tip, else
    its own) and one probe unless its spring gives ``sides``.  The body's
    bone ``names``, ``parents`` and inverse ``binds``; :class:`ValueError`
    names a bone the body hasn't or whose parent isn't the recipe's
    (D35)."""
    from azurkit.tools.characters.jiggle import Placed

    out = []
    for jb in bones:
        if jb.bone not in names:
            raise ValueError(f"jiggle.springs {jb.role!r}: the body has no bone {jb.bone!r}")
        k = names.index(jb.bone)
        p = parents[k]
        if p < 0 or names[p] != jb.parent:
            raise ValueError(f"jiggle.springs {jb.role!r}: {jb.bone}'s parent is "
                             f"{names[p] if p >= 0 else 'none'}, not {jb.parent!r}")
        kids = [c for c, q in enumerate(parents) if q == k]
        at = _inverse4(binds[kids[0] if len(kids) == 1 else k])
        if at is None:
            raise ValueError(f"jiggle.springs {jb.role!r}: {jb.bone}'s bind can't be inverted")
        out.append(Placed(jb, k, p, tuple(at[12:15]), 0.0, (0.0, 0.0, 0.0), {}, 0.0))
    return out


def rows(placed, springs: dict, binds, kappa: float = 1.0, parents=None) -> list[Row]:
    """The spring rows of ``placed`` bones (each a
    :class:`~azurik_mod.assets.jiggle.Placed`: W29's, and
    :func:`spring_places`') that ``springs`` (role ->
    :class:`Spring`) names, in index order, on a body whose inverse binds
    are ``binds`` (:func:`~azurik_mod.assets.characters.inverse_binds`)
    and bone ``parents`` (``None``: each row's own parent only), at
    stiffness slider ``kappa``; a row whose bone descends from another
    row's chains to it (its ``chain``).  :class:`ValueError` names a row
    past :data:`MAX_ROWS`, a body past :data:`MAX_BONES` bones, two rows
    on one bone or a bone whose bind can't be inverted (D35)."""
    if len(binds) > MAX_BONES:
        raise ValueError(f"jiggle: the body has {len(binds)} bones, past X41's {MAX_BONES}")
    seen = [pl.index for pl in placed if pl.bone.role in springs]
    if len(set(seen)) < len(seen):
        raise ValueError("jiggle: two spring rows take one bone")
    out = []
    for pl in sorted(placed, key=lambda pl: pl.index):
        spring = springs.get(pl.bone.role)
        if spring is None:
            continue
        ib = tuple(struct.unpack("<16f", struct.pack("<16f", *binds[pl.index])))
        wbind = _inverse4(ib)
        if wbind is None or not all(math.isfinite(x) for x in wbind):
            raise ValueError(f"jiggle: {pl.bone.role}'s bone {pl.bone.bone} has an inverse bind that can't be "
                             "inverted")
        origin = tuple(wbind[12:15])
        centre = spring.centre if spring.centre is not None else tuple(pl.origin)
        pivot = origin if spring.pivot == "origin" else tuple(c + p for c, p in zip(centre, spring.pivot))
        sides = pl.sides if spring.sides is None else spring.sides
        row_of = {r.bone: n for n, r in enumerate(out)}
        up = pl.parent
        while up >= 0 and up not in row_of:
            up = parents[up] if parents is not None and up < len(parents) else -1
        out.append(Row(pl.bone.role, pl.index, pl.parent, spring, coefficients(spring, kappa), centre, sides,
                       pivot, ib, wbind, row_of.get(up, -1)))
    if len(out) > MAX_ROWS:
        raise ValueError(f"jiggle: {len(out)} spring rows, past X41's {MAX_ROWS}")
    return out


def table(rows_: list[Row], bones: int, kappa: float = 1.0, drawn: float = 1.0) -> bytes:
    """X41's table (:data:`TABLE_SIZE` bytes) for ``rows_`` on a body of
    ``bones`` bones; ``kappa`` and ``drawn`` are recorded."""
    head = bytearray(HEADER_SIZE)
    struct.pack_into("<4sIIId", head, 0, MAGIC, len(rows_), bones, 0, H)
    struct.pack_into("<ff", head, 24, *_f32s(kappa, drawn))
    for n, r in enumerate(rows_):
        head[32 + r.bone] = n + 1
    body = bytearray(MAX_ROWS * ROW_SIZE)
    for n, r in enumerate(rows_):
        at = n * ROW_SIZE
        c, s = r.coeffs, r.spring
        struct.pack_into("<iiII", body, at, r.bone, r.parent, r.flags, r.chain + 1)
        struct.pack_into("<17d", body, at + 16, *c.phi_land, *c.gamma_land, *c.phi_swim, *c.gamma_swim, c.alpha,
                         c.g_land, c.g_swim, c.sag_land, c.sag_swim)
        struct.pack_into("<30f", body, at + 152, *_f32s(s.accel, s.gain, *s.travel, *s.weights, *r.centre, *r.pivot,
                                                         r.sides, s.turn, s.rot_share, s.pace, *s.squash, s.kick,
                                                         s.kick_hold, s.kick_time, s.impact, 0.0,
                                                         *(s.wall or (0.0,) * 4)))
        struct.pack_into("<16f16f", body, at + 272, *r.ib, *_f32s(*r.wbind))
    return bytes(head + body)


def _f32(x: float) -> float:
    """``x`` as float32 holds it (saturating past FLT_MAX, as the game's
    float stores do)."""
    if math.isfinite(x) and abs(x) > 3.4028234663852886e38:
        x = math.copysign(math.inf, x)
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _f32s(*xs: float) -> tuple[float, ...]:
    return tuple(_f32(x) for x in xs)


# --------------------------------------------------------------------------- the twin
def _packed(row: Row) -> Row:
    """``row`` with every number the table holds as float32 as float32
    holds it, as the shim reads them."""
    s = row.spring
    spring = replace(s, accel=_f32(s.accel), gain=_f32(s.gain), travel=_f32s(*s.travel), weights=_f32s(*s.weights),
                     turn=_f32(s.turn), rot_share=_f32(s.rot_share), pace=_f32(s.pace), squash=_f32s(*s.squash),
                     kick=_f32(s.kick), kick_hold=_f32(s.kick_hold), kick_time=_f32(s.kick_time),
                     impact=_f32(s.impact),
                     wall=None if s.wall is None else _f32s(*s.wall))
    return replace(row, spring=spring, centre=_f32s(*row.centre), pivot=_f32s(*row.pivot), sides=_f32(row.sides),
                   wbind=_f32s(*row.wbind))


def _mul4(a, b) -> list[float]:
    return [sum(a[4 * r + k] * b[4 * k + c] for k in range(4)) for r in range(4) for c in range(4)]


def _qrow(q) -> list[list[float]]:
    """The rotation of unit quaternion ``q`` (x, y, z, w) as a row-vector
    3x3 (v' = v R)."""
    x, y, z, w = q
    return [[1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + z * w), 2.0 * (x * z - y * w)],
            [2.0 * (x * y - z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + x * w)],
            [2.0 * (x * z + y * w), 2.0 * (y * z - x * w), 1.0 - 2.0 * (x * x + y * y)]]


def _soft(n: float, stop: float) -> float:
    if n <= KNEE * stop:
        return n
    x = (n - KNEE * stop) / ((1.0 - KNEE) * stop)
    return KNEE * stop + (1.0 - KNEE) * stop * x / (1.0 + x)


def _soft1(a: float, stop: float) -> float:
    if not stop > 0.0:
        return 0.0
    return _soft(a, stop) if a >= 0.0 else -_soft(-a, stop)


def _soft3(e: list[float], stops: list[float]) -> tuple[list[float], float]:
    """``e`` through the ellipsoid limit of ``stops`` (an axis with no
    stop shows 0); and its raw radius over them."""
    r2 = 0.0
    for i in range(3):
        if stops[i] > 0.0:
            q = e[i] / stops[i]
            r2 += q * q
        else:
            e[i] = 0.0
    r = math.sqrt(r2)
    if r <= KNEE:
        return e, r
    x = (r - KNEE) / (1.0 - KNEE)
    m = (KNEE + (1.0 - KNEE) * x / (1.0 + x)) / r
    return [c * m for c in e], r


@dataclass
class _State:
    u: list = field(default_factory=lambda: [[0.0] * 3, [0.0] * 3])
    v: list = field(default_factory=lambda: [[0.0] * 3, [0.0] * 3])
    prev: list = field(default_factory=lambda: [[0.0] * 3, [0.0] * 3])
    vf: list = field(default_factory=lambda: [[0.0] * 3, [0.0] * 3])
    acc: float = 0.0
    q: list | None = None
    live: bool = False
    warm: bool = False
    mode: int = 0
    swim: bool = False
    qprev: list = field(default_factory=lambda: [[0.0] * 3, [0.0] * 3])
    qaprev: list = field(default_factory=lambda: [[0.0] * 3, [0.0] * 3])
    mprev: list | None = None
    wa: list | None = None
    wo: list | None = None
    stamp: int = -1
    land: list = field(default_factory=lambda: [0.0, 0.0])   # a landing's push still to give, m/s
    lt: list = field(default_factory=lambda: [-1.0, -1.0])   # s since its landing (-1: none open)
    hard: list = field(default_factory=lambda: [False, False])   # it met the ground in a hard landing
    rate: list = field(default_factory=lambda: [0.0, 0.0])   # its push, m/s^2
    air: float = -1.0   # s since she was in the air (< 0: longer than LAND_TIME)


@dataclass(frozen=True)
class Shown:
    """What a row shows after a step: the centre's offset (mm as drawn,
    the bind axes side, forward, up), roll and yaw (rad), the raw radius
    over the travel, the clock and the squash's scales along the bind
    axes (1 each: none)."""

    offset: Vec
    roll: float
    yaw: float
    raw: float
    now: float
    scale: Vec = (1.0, 1.0, 1.0)


@dataclass(frozen=True)
class Pose:
    """One pose build as the shim sees it: the anim object, player and
    controller (any hashable ids), the clock, the drawn scale, 0x42200's
    raw matrix (16 floats; ``None`` when the shim wouldn't call it), the
    jiggle bones' worlds as the game posed them (bone -> 16 floats; a
    chained row's as its clip poses it, before its parent row's swing),
    the physics' velocity, the glide mode, the move state and the layers'
    weighted rate (clip seconds a second: :func:`layer_rate`)."""

    anim: object
    player: object
    control: object
    now: float
    scale: float
    m_raw: tuple | None
    worlds: dict
    velocity: Vec = (0.0, 0.0, 0.0)
    mode: int = 0
    state: int = 0
    rate: float = 1.0


def layer_rate(layers) -> float:
    """The anim's layers' weighted rate as X41 reads it: each playing
    layer's (flags at +8 not 0) rate (+0x20) by its weight (+0x1C), over
    their weights' sum (1 when it is 0); ``layers`` (flags, weight, rate)
    in the anim's order, float32 as the game holds them."""
    ws = wr = 0.0
    for flags, weight, rate in layers:
        if flags:
            ws += weight
            wr += weight * rate
    return wr / ws if ws > 0.0 else 1.0


class Twin:
    """X41's arithmetic in Python float64, step for step: :meth:`pose`
    takes a :class:`Pose` and returns each spring bone's world as the
    shim leaves it (absent: the game's); :attr:`shown` the rows' last
    :class:`Shown`, :attr:`steps` and :attr:`resets` the shim's counters,
    :attr:`kick_t`, :attr:`kicking`, :attr:`running`, :attr:`armed` and
    :attr:`kicks` its run-start clock (``player_model_jiggle_kick``);
    :attr:`tips` per walled row its centre's offset off the clip's pose
    after a step (the bind axes, mm as drawn: its parents' swing and its
    own; ``None`` without a wall), the preview's, not the shim's."""

    def __init__(self, rows_: list[Row], bones: int, strength: float = 1.0, h: float = H):
        self.rows, self.bones, self.h = [_packed(r) for r in rows_], bones, h
        self.strength = _f32(strength)
        self.states = [_State() for _ in rows_]
        self.last: tuple | None = None
        self.clock: float | None = None
        self.dt = 0.0
        self.m: list[float] | None = None
        self.steps = self.resets = self.builds = 0
        self.shown: list[Shown | None] = [None] * len(rows_)
        self.tips: list[tuple | None] = [None] * len(rows_)
        self.kick_t, self.kicking, self.running, self.armed, self.kicks = 0.0, False, False, False, 0

    def _reset(self) -> None:
        for st in self.states:
            st.live, st.q = False, None
        self.kicking = self.armed = False
        self.resets += 1

    def _kick_clock(self, p: Pose) -> None:
        """A step's run-start clock: on, at 0, the step she moves off
        (:data:`START` on the ground) after standing (:data:`REST`);
        counting the steps' time while she moves on the ground; off
        otherwise, and disarmed off the ground until she stands again;
        :attr:`running` at :data:`RUN_ON`."""
        vx, vy = _f32(p.velocity[0]), _f32(p.velocity[1])
        ground, sp2 = p.state == 0, vx * vx + vy * vy
        if self.kicking:
            self.kick_t += self.dt
        if not ground or sp2 < START * START:
            self.kicking = False
        if not ground:
            self.armed = False
        if ground and sp2 < REST * REST:
            self.armed = True
        elif self.armed and ground and sp2 >= START * START:
            self.kicking, self.armed, self.kick_t = True, False, 0.0
            self.kicks += 1
        self.running = sp2 >= RUN_ON * RUN_ON

    def pose(self, p: Pose) -> dict:
        """The worlds the shim leaves for ``p`` (bone -> 16 floats as
        float32 holds them): its own rows' written ones and a chained
        row's as the game builds it from its parent row's; a bone it
        leaves as the game posed it is absent."""
        if not self.rows or not (p.scale > 0.0 or p.scale < 0.0):
            return {}
        now = p.now
        if (self.last != (p.anim, p.player, p.control) or not math.isfinite(now)
                or (self.clock is not None and not now >= self.clock)):
            self._reset()
            self.last, self.clock = (p.anim, p.player, p.control), now
            return {}
        stepping = now != self.clock
        if stepping:
            s = p.scale
            m = [_f32(p.m_raw[4 * r + c] * s) if r < 3 else p.m_raw[4 * r + c] for r in range(4) for c in range(4)]
            if not all(math.isfinite(x) for x in m):
                self._reset()
                self.clock = now
                return {}
            self.m, self.dt, self.clock = m, now - self.clock, now
            self.steps += 1
            self._kick_clock(p)
        self.builds += 1
        out = {}
        for n, row in enumerate(self.rows):
            w, wa = list(p.worlds[row.bone]), None
            st = self.states[n]
            if row.chain >= 0:   # built by the game from the parent row's written world
                ps = self.states[row.chain]
                if ps.stamp == self.builds and ps.wo is not None:
                    back = _inverse4(p.worlds[self.rows[row.chain].bone])
                    if back is not None:
                        w = [_f32(x) for x in _mul4(_mul4(w, back), ps.wo)]
                        out[row.bone] = w
                    inv = _inverse4(ps.wo)
                    if inv is not None:
                        wa = _mul4(_mul4(w, inv), ps.wa)
            if stepping:
                self._step(n, row, st, w, p, wa)
            st.stamp, st.wa, st.wo = self.builds, w if wa is None else wa, None   # as the clip poses it
            if st.q is not None:
                new = [_f32(x) for x in _mul4(st.q, w)]
                if all(math.isfinite(x) for x in new):
                    out[row.bone] = st.wo = new
        return out

    def _step(self, n: int, row: Row, st: _State, w, p: Pose, wa=None) -> None:
        c, s = row.coeffs, row.spring
        if c.rests:
            st.q = None
            return
        x = _mul4(row.ib, w)
        xa = _mul4(row.ib, wa) if wa is not None else x
        xm = _mul4(x, self.m)
        two = row.flags & TWO_PROBES
        pts, qs, qa = [], [], []
        for side in ((-row.sides, row.sides) if two else (0.0,)):
            cp = (row.centre[0] + side, row.centre[1], row.centre[2])
            pts.append([cp[0] * xm[j] + cp[1] * xm[4 + j] + cp[2] * xm[8 + j] + xm[12 + j] for j in range(3)])
            qs.append([cp[0] * x[j] + cp[1] * x[4 + j] + cp[2] * x[8 + j] + x[12 + j] for j in range(3)])
            qa.append([cp[0] * xa[j] + cp[1] * xa[4 + j] + cp[2] * xa[8 + j] + xa[12 + j] for j in range(3)])
        dn = (-xm[8], -xm[9], -xm[10])
        dl = math.sqrt(dn[0] * dn[0] + dn[1] * dn[1] + dn[2] * dn[2])
        if not dl > 0.0 or not math.isfinite(dl):
            st.live, st.q = False, None
            return
        down = (dn[0] / dl, dn[1] / dl, dn[2] / dl)
        swim = p.state == SWIM_STATE or (p.state == HIT_STATE and st.live and st.swim)
        st.swim = swim
        phi, gam = (c.phi_swim, c.gamma_swim) if swim else (c.phi_land, c.gamma_land)
        g, sag = (c.g_swim, c.sag_swim) if swim else (c.g_land, c.sag_land)
        np_ = len(pts)
        if not st.live:
            for k in range(np_):
                st.u[k] = [sag * down[i] for i in range(3)]
                st.v[k] = [0.0, 0.0, 0.0]
                st.prev[k] = list(pts[k])
            st.live, st.warm, st.mode, st.acc, st.q = True, True, p.mode, 0.0, None
            st.lt, st.air = [-1.0, -1.0], 0.0 if p.state == AIR_STATE else -1.0
            st.qprev, st.qaprev, st.mprev = [list(q) for q in qs], [list(q) for q in qa], list(self.m)
            self.shown[n] = Shown((0.0, 0.0, 0.0), 0.0, 0.0, 0.0, p.now)
            return
        dt = self.dt
        if p.state == AIR_STATE:   # in the air: a landing may begin until LAND_TIME after
            st.air = 0.0
        elif st.air >= 0.0:
            st.air += dt
            if st.air > LAND_TIME:
                st.air = -1.0
        if dt > GAP:
            for k in range(np_):
                for _ in range(GAP_STEPS):
                    self._substep(st, k, phi, gam, (0.0, 0.0, -g))
            st.acc = 0.0
            st.lt = [-1.0, -1.0]
            for k in range(np_):
                st.prev[k] = list(pts[k])
            st.mode = p.mode
            st.qprev, st.qaprev, st.mprev = [list(q) for q in qs], [list(q) for q in qa], list(self.m)
        else:
            st.acc += dt
            steps = 0
            while steps < MAX_SUBSTEPS and st.acc > self.h * SUBSTEP_EDGE:
                st.acc -= self.h
                steps += 1
            jump = p.mode != st.mode
            for k in range(np_):
                d = [pts[k][i] - st.prev[k][i] - p.velocity[i] * dt for i in range(3)]
                if d[0] * d[0] + d[1] * d[1] + d[2] * d[2] > TELEPORT * TELEPORT:
                    jump = True
            acc = [[0.0, 0.0, 0.0] for _ in range(np_)]
            if st.warm:
                for k in range(np_):
                    st.vf[k] = [(pts[k][i] - st.prev[k][i]) / dt for i in range(3)]
                st.warm = False
            elif not jump:
                keep = 1.0
                for _ in range(steps):
                    keep *= 1.0 - c.alpha
                share = 1.0 - keep
                pace = pace_factor(p.rate, s.pace)
                mp = st.mprev
                ke = (1.0 - self.kick_t / s.kick_time if self.kicking and self.running and s.kick_time > 0.0
                      and self.kick_t < s.kick_time else 0.0)   # a run's start: its kick, tapering
                for k in range(np_):
                    qp, qap = st.qprev[k], st.qaprev[k]
                    frame = [qp[0] * (self.m[j] - mp[j]) + qp[1] * (self.m[4 + j] - mp[4 + j])
                             + qp[2] * (self.m[8 + j] - mp[8 + j]) + (self.m[12 + j] - mp[12 + j]) for j in range(3)]
                    da = [qa[k][i] - qap[i] for i in range(3)]
                    dj = [(qs[k][i] - qa[k][i]) - (qp[i] - qap[i]) for i in range(3)]
                    posed = [da[0] * self.m[j] + da[1] * self.m[4 + j] + da[2] * self.m[8 + j] for j in range(3)]
                    swung = [dj[0] * self.m[j] + dj[1] * self.m[4 + j] + dj[2] * self.m[8 + j] for j in range(3)]
                    fall = st.vf[k][2]
                    for i in range(3):
                        va = (pts[k][i] - st.prev[k][i] if pace == 1.0
                              else frame[i] + pace * posed[i] + swung[i]) / dt
                        nf = st.vf[k][i] + (va - st.vf[k][i]) * share
                        acc[k][i] = (nf - st.vf[k][i]) / dt
                        st.vf[k][i] = nf
                    if ke > 0.0 and s.kick_hold != 0.0:   # the level drive held, to none at most
                        level = 1.0 - s.kick_hold * ke
                        level = level if level > 0.0 else 0.0
                        acc[k][0] *= level
                        acc[k][1] *= level
                    if s.accel > 0.0:
                        a2 = acc[k][0] * acc[k][0] + acc[k][1] * acc[k][1] + acc[k][2] * acc[k][2]
                        f = 1.0 / math.sqrt(1.0 + a2 / (s.accel * s.accel))
                        acc[k] = [a * f for a in acc[k]]
                    if ke > 0.0 and s.kick != 0.0:   # her first footfalls' push raised
                        acc[k][2] *= 1.0 + s.kick * ke
                    if s.impact > 0.0:   # a landing: its up push keyed on the speed it met the ground at
                        if (st.lt[k] < 0.0 and p.state != AIR_STATE and st.air >= 0.0 and fall < -IMPACT_FALL
                                and st.vf[k][2] > fall):
                            st.land[k], st.lt[k], st.hard[k] = s.impact * -fall, 0.0, p.state == HARD_STATE
                            st.rate[k] = st.land[k] / LAND_TIME
                        if st.lt[k] >= 0.0:   # spread evenly over LAND_TIME along her up as drawn, the own held
                            d = min(st.land[k], st.rate[k] * dt)
                            st.land[k] -= d
                            acc[k][2] = 0.0
                            acc[k] = [acc[k][i] - d / dt * down[i] for i in range(3)]
                            st.lt[k] += dt
                            if st.lt[k] >= LAND_TIME and not (st.hard[k] and p.state == HARD_STATE):
                                st.lt[k] = -1.0
            for k in range(np_):
                st.prev[k] = list(pts[k])
            st.mode = p.mode
            st.qprev, st.qaprev, st.mprev = [list(q) for q in qs], [list(q) for q in qa], list(self.m)
            for k in range(np_):
                force = (-acc[k][0], -acc[k][1], -g - acc[k][2])
                for _ in range(steps):
                    self._substep(st, k, phi, gam, force)
        bound = BOUND * max(s.travel)
        for k in range(np_):
            dd = [st.u[k][i] - sag * down[i] for i in range(3)]
            r = math.sqrt(dd[0] * dd[0] + dd[1] * dd[1] + dd[2] * dd[2])
            if bound > 0.0 and r > bound:
                nh = [d / r for d in dd]
                st.u[k] = [sag * down[i] + nh[i] * bound for i in range(3)]
                vr = st.v[k][0] * nh[0] + st.v[k][1] * nh[1] + st.v[k][2] * nh[2]
                if vr > 0.0:
                    st.v[k] = [st.v[k][i] - (1.0 + RESTITUTION) * vr * nh[i] for i in range(3)]
        if not all(math.isfinite(z) for k in range(np_) for arr in (st.u[k], st.v[k], st.vf[k], st.prev[k])
                   for z in arr):
            st.live, st.q = False, None
            return
        inv = _inverse3([[xm[4 * r + cc] for cc in range(3)] for r in range(3)])
        if inv is None:
            st.q = None
            return
        scale = abs(p.scale)
        stops = [t / scale for t in s.travel]
        k_gain = self.strength * s.gain
        nw = s.wall[:3] if s.wall is not None else (0.0, 0.0, 0.0)
        walled = (nw[0] != 0.0 or nw[1] != 0.0 or nw[2] != 0.0) and k_gain != 0.0
        # the axis's part of the offset per unit of the mass's move
        gw = [inv[i][0] * s.weights[0] * nw[0] + inv[i][1] * s.weights[1] * nw[1] + inv[i][2] * s.weights[2] * nw[2]
              for i in range(3)]
        gg = gw[0] * gw[0] + gw[1] * gw[1] + gw[2] * gw[2]
        es, hs, raw = [], [], 0.0
        for k in range(np_):
            lim = 0.0
            if walled:   # the allowance: the stop less its parents' swing toward her off the clip's pose
                hw = [(qs[k][0] - qa[k][0]) * self.m[j] + (qs[k][1] - qa[k][1]) * self.m[4 + j]
                      + (qs[k][2] - qa[k][2]) * self.m[8 + j] for j in range(3)]
                hb = [hw[0] * inv[0][j] + hw[1] * inv[1][j] + hw[2] * inv[2][j] for j in range(3)]
                lim = s.wall[3] / scale - sum(hb[j] * nw[j] for j in range(3))
                hs.append(hb)
            e = self._shape(st.u[k], k_gain, self.strength, sag, down, inv, s.weights)
            if walled and gg > 0.0:   # the part past it off the mass, its inward speed bounced
                over = e[0] * nw[0] + e[1] * nw[1] + e[2] * nw[2] - lim
                if over > 0.0:
                    cw, vr = over / (k_gain * gg), st.v[k][0] * gw[0] + st.v[k][1] * gw[1] + st.v[k][2] * gw[2]
                    st.u[k] = [st.u[k][i] - cw * gw[i] for i in range(3)]
                    if k_gain * vr > 0.0:
                        st.v[k] = [st.v[k][i] - (1.0 + RESTITUTION) * vr / gg * gw[i] for i in range(3)]
                    e = self._shape(st.u[k], k_gain, self.strength, sag, down, inv, s.weights)
            e, r = _soft3(e, stops)
            raw = max(raw, r)
            if walled:   # the shown offset held to it
                over = e[0] * nw[0] + e[1] * nw[1] + e[2] * nw[2] - lim
                if over > 0.0:
                    e = [e[i] - over * nw[i] for i in range(3)]
            es.append(e)
        self.tips[n] = (tuple(sum(hs[k][i] + es[k][i] for k in range(np_)) / np_ * scale * 1000.0 for i in range(3))
                        if walled else None)
        if np_ == 2:
            delta = [(es[0][i] + es[1][i]) * 0.5 for i in range(3)]
            span = 2.0 * row.sides
            roll = _soft1((es[0][2] - es[1][2]) / span, s.turn)
            yaw = _soft1((es[1][1] - es[0][1]) / span, s.turn)
        else:
            delta, roll, yaw = es[0], 0.0, 0.0
        sq = _squash(delta, stops, s.squash)
        q = _offset(delta, roll, yaw, row.centre, row.pivot, s.rot_share, sq)
        qb = None if q is None else _mul4(_mul4(row.wbind, q), row.ib)
        st.q = qb if qb is not None and all(math.isfinite(z) for z in qb) else None
        self.shown[n] = Shown(tuple(d * scale * 1000.0 for d in delta), roll, yaw, raw, p.now, tuple(sq))

    @staticmethod
    def _shape(u, k_gain: float, strength: float, sag: float, down, inv, weights) -> list[float]:
        """A probe's offset in the bind axes from its mass: the gain on the
        springs' motion (the mass from its world rest), the hang (the world
        rest from the bone's turned one) at the strength."""
        dw = [k_gain * (u[i] + (sag if i == 2 else 0.0)) + strength * sag * ((-1.0 if i == 2 else 0.0) - down[i])
              for i in range(3)]
        dk = [dw[0] * inv[0][j] + dw[1] * inv[1][j] + dw[2] * inv[2][j] for j in range(3)]
        return [weights[j] * dk[j] for j in range(3)]

    @staticmethod
    def _substep(st: _State, k: int, phi, gam, force) -> None:
        a, b, c, d = phi
        g0, g1 = gam
        for i in range(3):
            u, v = st.u[k][i], st.v[k][i]
            st.u[k][i] = a * u + b * v + g0 * force[i]
            st.v[k][i] = c * u + d * v + g1 * force[i]


SQUASH_LIMIT = 1.0
"""A squash's exponent is softly limited at +-this (a factor e at most)."""


def _squash(delta, stops, squash) -> list[float]:
    """The form's scales along the bind axes (D481): ``eps_i`` =
    ``squash[i]`` x the offset along i over its stop (0 on an axis with
    none), each scale ``e^(eps_i - (eps_j + eps_k) / 2)`` with the
    exponent softly limited at :data:`SQUASH_LIMIT`, so the three
    multiply to 1 (its volume kept)."""
    eps = [squash[i] * delta[i] / stops[i] if stops[i] > 0.0 else 0.0 for i in range(3)]
    return [_exp(_soft1(eps[i] - 0.5 * (eps[(i + 1) % 3] + eps[(i + 2) % 3]), SQUASH_LIMIT))
            if eps[0] != 0.0 or eps[1] != 0.0 or eps[2] != 0.0 else 1.0 for i in range(3)]


def _offset(delta, roll: float, yaw: float, centre, pivot, share: float, scale=None):
    """The move O (16 floats, D3D rows, the bind frame) taking the centre
    exactly by ``delta``: ``scale`` (the squash's, along the bind axes)
    about the centre, then the twist (roll about y, yaw about z) about the
    centre, a swing about ``pivot`` taking ``share`` of the offset across
    the pivot's arm as a rotation, the rest a translation.  ``None`` when
    anything isn't finite."""
    vals = (*delta, roll, yaw)
    if not all(math.isfinite(z) for z in vals):
        return None
    qx, qy, qz, qw = 0.0, roll * 0.5, yaw * 0.5, 1.0
    nq = math.sqrt(qy * qy + qz * qz + 1.0)
    rt = _qrow((qx, qy / nq, qz / nq, qw / nq))
    r = [centre[i] - pivot[i] for i in range(3)]
    rr = r[0] * r[0] + r[1] * r[1] + r[2] * r[2]
    rs = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    if rr > 0.0 and share != 0.0:
        along = (delta[0] * r[0] + delta[1] * r[1] + delta[2] * r[2]) / rr
        b = [r[i] + share * (delta[i] - along * r[i]) for i in range(3)]
        cx = (r[1] * b[2] - r[2] * b[1], r[2] * b[0] - r[0] * b[2], r[0] * b[1] - r[1] * b[0])
        w = math.sqrt(rr * (b[0] * b[0] + b[1] * b[1] + b[2] * b[2])) + r[0] * b[0] + r[1] * b[1] + r[2] * b[2]
        nn = math.sqrt(cx[0] * cx[0] + cx[1] * cx[1] + cx[2] * cx[2] + w * w)
        if nn > 0.0:
            rs = _qrow((cx[0] / nn, cx[1] / nn, cx[2] / nn, w / nn))
    rot = [[sum(rt[i][k] * rs[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
    rsr = [sum(r[k] * rs[k][j] for k in range(3)) for j in range(3)]
    t = [delta[j] - (rsr[j] - r[j]) for j in range(3)]
    crt = [sum(centre[k] * rt[k][j] for k in range(3)) for j in range(3)]
    lead = [centre[j] - crt[j] - pivot[j] for j in range(3)]
    tr = [sum(lead[k] * rs[k][j] for k in range(3)) + pivot[j] + t[j] for j in range(3)]
    o = [rot[0][0], rot[0][1], rot[0][2], 0.0, rot[1][0], rot[1][1], rot[1][2], 0.0,
         rot[2][0], rot[2][1], rot[2][2], 0.0, tr[0], tr[1], tr[2], 1.0]
    if scale is None or scale[0] == scale[1] == scale[2] == 1.0:
        return o
    if not all(math.isfinite(z) for z in scale):
        return None
    sc = [scale[0], 0.0, 0.0, 0.0, 0.0, scale[1], 0.0, 0.0, 0.0, 0.0, scale[2], 0.0,
          centre[0] * (1.0 - scale[0]), centre[1] * (1.0 - scale[1]), centre[2] * (1.0 - scale[2]), 1.0]
    return _mul4(sc, o)


# --------------------------------------------------------------------------- the preview
V0 = 4.6432748
"""Vanilla's jump speed, m/s (the preview's jump)."""
WALK_SPEEDS = (3.5, 4.0, 4.9)
"""The walk slot's ground speeds the preview plays (half tilt, the bake's
4.0, the walk/run switch's edge), m/s."""
LOOP_TOLERANCE = (0.02, 0.05)
"""A clip whose bones' chain ends this near where it starts (model units,
its world rotation's components) plays as a loop in the preview."""
TARGETS = {
    "idle": "the bust and the glutes at most 5 mm",
    "run": "the bust's peak 25-120 mm, the glutes' at least 13 mm",
    "stop": "the bust forward 30-120 mm with at least 3 extrema over 5 mm",
    "landing": "a jump's landing (its ring from touchdown): the bust 40-100 mm, raw at most 1.1 x travel (no saturated "
               "plateau), at least 3 extrema over 10 mm; the glutes at least 2 extrema over 5 mm; a 3.5 m drop's "
               "bust at least 1.2 x the jump's (D619: a landing scales with the fall)",
    "walk": "every walk slot and climb loop (its root's travel carried): the bust's and the glutes' largest tick "
            "move at most 50 mm",
    "rate": "the run's, stop's and landing's peaks (a walled row's: its tip's peak to peak over 10 mm) within 15% "
            "between 30 and 60 Hz",
    "start": "a run from standing: the bust's side and forward peaks at most a third of its up peak (its first "
             "strides bounce, not swing: AZ-678)",
    "chain": "the cloth (Step 2.169b): every walled tip at most its stop + 0.1 mm nearer her than the clip poses it in "
             "every run at 30 and 60 Hz; each hem's run 40-200 mm peak to peak; a stop swings it at least 20 mm (along "
             "its largest swing's bind axis) and from 1.5 s on it is back within 5 mm of its idle's reach",
}
"""DESIGN 5.4's acceptance targets (Step 2.156; the glutes' ring the
critique's, D115), which :func:`preview` marks: the run's band DESIGN
11's 25-45 mm (tuning sitting 1's judge: D498's 15-45 passed a bob the
owner had called no jiggle; a softer cap under a higher gain buys the
run's bounce at the same landing), the landing's as tuning sitting 1 set
it (D498: a landing that saturates its travel snaps from plateau to
plateau, D481's "smooth and squishy" wants it linear), judged on its
ring from touchdown (Step 2.174: the jump's takeoff, past the knee of
the old up travel, is no landing) and growing with the fall (D619); the
idle and walk targets judge the bust and the glutes (a chain's links
sway); the start's, Step 2.156b's kick (D518).  Step 2.171 raised the
run's and stop's ceilings to 120 mm and the walk's tick to 50 mm (D583:
her own gait bounces her bust and butt "a lot"; D584: her walk's bust
"a lot more"), their floors kept, so a body on its base clips passes as
before, and dropped the walk's "at most half the ticks over 10 mm"
(AZ-648's metric, still printed: her v4 bust's 3.5 m/s walk moves over
10 mm on 76 of its 121 ticks); the chain's, Step 2.169b's design (D536, [inferred]).  Each judges
every row of its kind (:func:`kinds`): the form targets every bust and
glutes row (v4's two breasts and two glutes), the chain's the cloth's."""


@dataclass(frozen=True)
class Run:
    """One preview row: per spring row its peak |offset| per axis (side,
    forward, up, mm), its peak radius, the largest move in a tick, how
    many ticks moved over 10 mm (of ``ticks``), its raw radius over the
    travel and its ring's extrema (mm along the row's ``axis``) after the
    event; per walled row (``chain``) its stop and its tip off the clip's
    pose (:attr:`Twin.tips`, mm): its largest move toward her, its peak
    to peak on the largest bind axis from the measure's start, its ring's
    extrema along the bind axis it swings most on (a wall damps the ring
    along its own), its largest offset 1.5 s after the ring starts and
    from the measure's start."""

    name: str
    hz: int
    ticks: int
    peak: dict
    radius: dict
    largest: dict
    over10: dict
    raw: dict
    extrema: dict
    chain: dict = field(default_factory=dict)


def _qmat(q, origin) -> list[float]:
    x, y, z, w = q
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    m = _qrow((x / n, y / n, z / n, w / n))
    return [m[0][0], m[0][1], m[0][2], 0.0, m[1][0], m[1][1], m[1][2], 0.0, m[2][0], m[2][1], m[2][2], 0.0,
            origin[0], origin[1], origin[2], 1.0]


def _drive(rows_: list[Row], bones: int, ticks: list[dict], strength: float, hz: int, axis: int = 1,
           after: float = 0.0, name: str = "", ring: float | None = None) -> Run:
    """Run the twin over ``ticks`` (each: the clock ``now``, the bones'
    worlds, the facing yaw, the origin, the velocity and the move state)
    and measure each row from ``after`` s on, its ring's extrema from
    ``ring`` s on (``None``: ``after``)."""
    twin = Twin(rows_, bones, strength)
    shown: dict[str, list] = {r.role: [] for r in rows_}
    raw = {r.role: 0.0 for r in rows_}
    tips: dict[str, list] = {r.role: [] for r in rows_ if r.spring.wall is not None}
    for t in ticks:
        m = _qmat((0.0, 0.0, fdlibm.sin(t["yaw"] / 2.0), fdlibm.cos(t["yaw"] / 2.0)), t["origin"])
        twin.pose(Pose("A", "P", "C", t["now"], t["scale"], m, t["worlds"], t["velocity"], 0, t["state"],
                       t.get("rate", 1.0)))
        for k, r in enumerate(rows_):
            sh = twin.shown[k]
            if t["now"] >= after and sh is not None:
                shown[r.role].append((t["now"], sh.offset))
                raw[r.role] = max(raw[r.role], sh.raw)
            if r.role in tips and twin.tips[k] is not None:
                tips[r.role].append((t["now"], twin.tips[k]))
    out = {key: {} for key in ("peak", "radius", "largest", "over10", "extrema")}
    for role, series in shown.items():
        offs = [o for _, o in series] or [(0.0, 0.0, 0.0)]
        out["peak"][role] = tuple(max(abs(o[i]) for o in offs) for i in range(3))
        out["radius"][role] = max(math.sqrt(sum(c * c for c in o)) for o in offs)
        steps = [math.dist(a, b) for a, b in zip(offs, offs[1:])] or [0.0]
        out["largest"][role] = max(steps)
        out["over10"][role] = sum(1 for d in steps if d > 10.0)
        vals = [o[axis] for t, o in series if t >= (after if ring is None else ring)]
        ext = [vals[i] for i in range(1, len(vals) - 1)
               if (vals[i] - vals[i - 1]) * (vals[i + 1] - vals[i]) < 0.0 and abs(vals[i]) > 0.5]
        out["extrema"][role] = tuple(ext[:8])
    chain = {}
    for r in rows_:
        if r.role not in tips:
            continue
        series, n = tips[r.role] or [(0.0, (0.0, 0.0, 0.0))], r.spring.wall[:3]
        late = [o for t, o in series if ring is not None and t >= ring + 1.5]
        measured = [o for t, o in series if t >= after] or [(0.0, 0.0, 0.0)]
        rung = [o for t, o in series if t >= (after if ring is None else ring)] or [(0.0, 0.0, 0.0)]
        span = [max(o[i] for o in rung) - min(o[i] for o in rung) for i in range(3)]
        vals = [o[span.index(max(span))] for o in rung]   # the ring along its largest swing's axis
        chain[r.role] = {
            "stop": r.spring.wall[3] * 1000.0, "inward": max(sum(o[i] * n[i] for i in range(3)) for _, o in series),
            "pp": max(max(o[i] for o in measured) - min(o[i] for o in measured) for i in range(3)),
            "extrema": tuple([vals[i] for i in range(1, len(vals) - 1)
                              if (vals[i] - vals[i - 1]) * (vals[i + 1] - vals[i]) < 0.0 and abs(vals[i]) > 0.5][:8]),
            "late": max((math.sqrt(sum(c * c for c in o)) for o in late), default=0.0),
            "reach": max(math.sqrt(sum(c * c for c in o)) for o in measured)}
    return Run(name, hz, len(ticks), out["peak"], out["radius"], out["largest"], out["over10"], raw, out["extrema"],
               chain)


def _closes(at, length: float) -> bool:
    (q0, o0), (q1, o1) = at(0.0), at(length)
    same = min(max(abs(a - b) for a, b in zip(q0, q1)), max(abs(a + b) for a, b in zip(q0, q1)))
    return same <= LOOP_TOLERANCE[1] and max(abs(a - b) for a, b in zip(o0, o1)) <= LOOP_TOLERANCE[0]


class _Poser:
    """The spring bones' worlds over a clip of the built body, as the
    engine poses them (:func:`~azurik_mod.assets.jiggle._posed` on each
    bone's chain: its rest values below its keyed parents); a clip whose
    ``loop_bones`` (W29's forms, else every row's bone) end where they
    start plays as a loop."""

    def __init__(self, characters: bytes, body: str, rows_: list[Row], loop_bones=None):
        from azurkit.tools.characters import jiggle as jg
        from azurkit.tools.characters.retarget import Rig

        self.characters, self.body, self.rows = characters, body, rows_
        self.rig = Rig.read(characters, body)
        self.chains = {r.bone: jg._chain(self.rig, r.bone) for r in rows_}
        self.loop_bones = list(loop_bones) if loop_bones else [r.bone for r in rows_]
        self._cache: dict = {}

    def clip(self, name: str):
        from azurkit.tools.characters import jiggle as jg
        from azurkit.tools.characters.retarget import named_clip

        if name not in self._cache:
            clip = named_clip(self.characters, self.body, name)
            ats = {k: jg._posed(self.rig, clip, chain) for k, chain in self.chains.items()}
            loop = all(_closes(ats[k], clip.length) for k in self.loop_bones)
            root = next(k for k, b in enumerate(self.rig.bones) if b.parent < 0)
            self._cache[name] = (clip.length, ats, loop, jg._posed(self.rig, clip, [root]))
        return self._cache[name][:3]

    def _at(self, name: str, t: float, carried: bool = False) -> dict:
        length, ats, loop = self.clip(name)
        t = t % length if loop and length > 0 else min(max(t, 0.0), length)
        shift = self.shift(name, t) if carried else (0.0, 0.0, 0.0)
        out = {}
        for k, at in ats.items():
            q, o = at(t)
            out[k] = (q, tuple(a - b for a, b in zip(o, shift)))
        return out

    def worlds(self, name: str, t: float, carried: bool = False) -> dict:
        """The bones' worlds at clip time ``t``; ``carried``: with the root
        bone's travel since the clip's start taken off (the critter
        carrying it, as the drawn body must be on a climb loop whose root
        shuffles along the rungs and snaps back at its seam)."""
        return {k: [_f32(v) for v in _qmat(q, o)] for k, (q, o) in self._at(name, t, carried).items()}

    def faded(self, old: str, t_old: float, new: str, t_new: float, since: float) -> dict:
        """The bones' worlds ``since`` s into the game's crossfade from
        ``old`` at ``t_old`` to ``new`` at ``t_new`` (``docs/RE_XBE.md`` §
        "The anim layers' crossfade": the new layer's weight 0.01 + since /
        :data:`FADE` over the two layers' sum); the game blends each bone's
        own pose, this each spring bone's world (its rotation's components
        summed by the weight on one hemisphere, its origin lerped), close
        over a 0.25 s fade."""
        if since >= FADE:
            return self.worlds(new, t_new)
        a, b = 0.01 + since / FADE, 1.0 - since / FADE
        w = a / (a + b)
        was, now = self._at(old, t_old), self._at(new, t_new)
        out = {}
        for k, (q1, o1) in now.items():
            q0, o0 = was[k]
            s = -1.0 if sum(x * y for x, y in zip(q0, q1)) < 0 else 1.0
            q = tuple((1.0 - w) * x * s + w * y for x, y in zip(q0, q1))
            out[k] = [_f32(v) for v in _qmat(q, tuple((1.0 - w) * x + w * y for x, y in zip(o0, o1)))]
        return out

    def shift(self, name: str, t: float) -> tuple:
        """The root bone's travel from the clip's start to clip time ``t``
        (one in the clip, as :meth:`worlds` wraps it): what ``carried``
        takes off every bone."""
        self.clip(name)
        root = self._cache[name][3]
        return tuple(a - b for a, b in zip(root(t)[1], root(0.0)[1]))


def _scenario(name: str, hz: int, poser: _Poser, slots: dict, rates: dict, scale: float):
    """A physics scenario's ticks (tune_sim's, on the body's own slot
    clips), the time its measure starts, the ring's axis and when its ring
    starts (the stop, the hit, the landing)."""
    dt, ticks = 1.0 / hz, []
    idle = slots.get(1) or next(iter(slots.values()))
    walk, run_clip = slots.get(8, idle), slots.get(9, slots.get(8, idle))
    run_rate = rates["run"]
    swim = slots.get(74) or slots.get(73) or idle
    x = y = 0.0
    z = 3.5 if name == "drop" else 0.0
    vy = vz = psi = 0.0
    landed = stopped = None
    for n in range(int(4.0 * hz) + 1):
        t = n * dt
        clip, ct, om, state, jump = idle, t, 0.0, 0, 0.0
        if name.startswith("walk"):
            vy, clip, ct = float(name[4:]) / 10.0, walk, t * rates[name]
        elif name in ("run", "place"):
            vy, clip, ct = 7.0, run_clip, t * run_rate
            if name == "place" and abs(t - 1.5) < dt / 2:
                jump = 6.8
        elif name == "start":
            if t >= 0.5:
                vy = min(7.0, vy + 98.0 * dt)
                clip, ct = run_clip, (t - 0.5) * run_rate
            else:
                clip, ct = run_clip, 0.0
        elif name == "stop":
            if t < 1.5:
                vy, clip, ct = 7.0, run_clip, t * run_rate
            else:
                vy = max(0.0, vy - 98.0 * dt)
                clip, ct = (run_clip, 1.5 * run_rate) if vy > 0 else (idle, t - 1.5)
                if vy == 0.0 and stopped is None:
                    stopped = t
        elif name in ("jump", "drop"):
            if 0.5 <= t and landed is None:
                if name == "jump" and vz == 0.0 and z == 0.0:
                    vz = V0
                else:
                    vz -= G * dt
                if z + vz * dt <= 0.0 and t > 0.6:
                    z, vz, landed = 0.0, 0.0, t
                else:
                    state = AIR_STATE   # as the game's move state is in the air (a landing's impact reads it)
        elif name == "spin":
            om = 31.0 if 0.5 <= t < 1.1 else 0.0
        elif name == "hit":
            vy = -4.0 * (1.0 - (t - 0.5) / 0.3) if 0.5 <= t < 0.8 else 0.0
        elif name == "swim":
            vy, clip, ct, state = 1.5, swim, t, SWIM_STATE
        if n:
            y += vy * dt + jump
            z += vz * dt
            psi += om * dt
        d = (-fdlibm.sin(psi) * vy, fdlibm.cos(psi) * vy, vz)
        rate = (rates[name] if name.startswith("walk") else run_rate if clip == run_clip and clip != idle
                else 1.0)
        worlds = (poser.faded(run_clip, 1.5 * run_rate, idle, ct, t - stopped) if stopped is not None
                  else poser.worlds(clip, ct))   # a stop crossfades into the idle as the game does
        ticks.append({"now": (n + 1) * dt, "worlds": worlds, "yaw": psi,
                      "origin": (x + 0.0, y, z), "velocity": d, "state": state, "scale": scale, "rate": rate})
    after = 1.0 if name.startswith("walk") or name == "run" else 0.0
    axis = {"stop": 1, "hit": 1, "jump": 2, "drop": 2}.get(name, 2)
    ring = {"stop": 1.5, "hit": 0.5}.get(name, landed - 0.1 if landed is not None else None)
    return ticks, after, axis, ring


CLIMB_LOOPS = (56, 57, 58, 59)
"""The ladder's climb loops' slots (climb_up, _down, _left, _right): the
preview plays each in place and carried (:meth:`_Poser.worlds`); the
targets judge the carried one, the sitting the game's (R10); :func:`pose`
plays the carried one."""
SCENARIOS = ("idle", "walk35", "walk40", "walk49", "run", "start", "stop", "jump", "drop", "spin", "hit", "place",
             "swim")


def simulate(springs: dict, *, strength: float = 1.0, hz: int = 30, clips: str | None = "all",
             scenarios=SCENARIOS) -> list[Run]:
    """The preview's runs (:class:`Run`) for a build's ``springs``
    (``apply_player_model``'s ``springs_out``): each physics scenario
    (:data:`SCENARIOS`, tune_sim's on the body's own slot clips: the walk
    slot at each of :data:`WALK_SPEEDS`, the run slot at garret4's run
    speed, a jump at :data:`V0`, a 3.5 m drop, a 31 rad/s spin, a
    knockback, a 6.8 m place and a swim stroke), then each slot's clip
    (``clips``: ``"all"``, one clip's name, or ``None``) at the rate the
    game plays it, standing, a loop for 3 s, a one-shot played once from
    rest and held 1 s."""
    rows_, scale = springs["rows"], springs["drawn"]
    poser, rates, slots = _poser(springs), _rates(springs), springs["slots"]
    bones = len(poser.rig.bones)
    out = []
    for name in scenarios:
        ticks, after, axis, ring = _scenario(name, hz, poser, slots, rates, scale)
        out.append(_drive(rows_, bones, ticks, strength, hz, axis, after, name, ring))
    wanted = sorted({c for c in slots.values()}) if clips == "all" else [] if clips is None else [clips]
    for clip in wanted:
        climb = poser.clip(clip)[2] and clip in {slots.get(k) for k in CLIMB_LOOPS}
        for carried in (False, True) if climb else (False,):
            rate, loop, ticks = _played(springs, rates, poser, clip, hz, carried)
            out.append(_drive(rows_, bones, ticks, strength, hz, 2, 1.0 if loop else 0.0,
                              f"clip {clip} x{rate:.3g}" + (" (loop, carried)" if carried else " (loop)" if loop
                                                            else "")))
    return out


def _poser(springs: dict) -> _Poser:
    """The :class:`_Poser` of a build's ``springs``: W29's forms decide
    whether a clip loops (a chain's links may not close)."""
    rows_ = springs["rows"]
    formed = {pl.bone.role for pl in springs.get("placed", ()) if pl.bone.shape}
    return _Poser(springs["characters"], springs["body"], rows_, [r.bone for r in rows_ if r.role in formed])


def _rates(springs: dict) -> dict:
    """The walk slot's clip rate at each of :data:`WALK_SPEEDS` and the run
    slot's at garret4's run speed, over the body's stride cells."""
    scale, cells = springs["drawn"], springs["cells"]
    stride = lambda cell, speed: speed / (scale * cell) if cell and speed and scale > 0 else 1.0  # noqa: E731
    rates = {f"walk{round(v * 10)}": stride(cells.get("walkAnimSpeed"), v) for v in WALK_SPEEDS}
    rates["run"] = stride(cells.get("runAnimSpeed"), cells.get("runSpeed"))
    return rates


def _played(springs: dict, rates: dict, poser: _Poser, clip: str, hz: int, carried: bool = False):
    """``clip`` played standing at the rate the game plays it (the walk
    slot's at 4.0 m/s, the run slot's at the run speed, any other at its
    playback rate): its rate, whether it loops and its ticks (a loop for
    3 s, a one-shot once from rest after 0.3 s and held 1 s), each with
    its clip time ``ct`` (a loop's wrapped, as :meth:`_Poser.worlds` plays
    it)."""
    slots = springs["slots"]
    length, _, loop = poser.clip(clip)
    rate = (rates["walk40"] if clip == slots.get(8) else rates["run"] if clip == slots.get(9)
            else springs["rates"].get(clip.casefold(), 1.0))
    play = length / rate if rate > 0 else length
    span = 3.0 if loop else 0.3 + play + 1.0
    ticks = []
    for n in range(int(span * hz) + 1):
        t = n / hz
        ct = (t * rate) % length if loop and length > 0 else min(max(t - 0.3, 0.0) * rate, length)
        ticks.append({"now": (n + 1) / hz, "ct": ct, "worlds": poser.worlds(clip, ct, carried), "yaw": 0.0,
                      "origin": (0.0, 0.0, 0.0), "velocity": (0.0, 0.0, 0.0), "state": 0, "scale": springs["drawn"],
                      "rate": rate})
    return rate, loop, ticks


@dataclass(frozen=True)
class Played:
    """One clip as :func:`pose` plays it: its name, its rate (clip seconds
    a second), whether it loops, whether it is carried (a climb loop,
    :data:`CLIMB_LOOPS`: its root's travel since the clip's start taken off
    every bone, as the game draws it), each tick's clock (s, the twin's:
    1/hz apart) and clip time, and every bone's world that tick (``(ticks,
    bones, 4, 4)`` float64: the model frame, column vectors, its scale in,
    as the body's inverse binds skin it)."""

    clip: str
    rate: float
    loop: bool
    carried: bool
    now: tuple
    time: tuple
    worlds: object


@dataclass(frozen=True)
class Posed:
    """:func:`pose`'s result: the body's bones (names, parents), their
    inverse binds (``(bones, 4, 4)``, column vectors), which bones a spring
    row moves (its own or one above it) and the clips played."""

    bones: tuple
    parents: tuple
    binds: object
    sprung: tuple
    clips: tuple

    def save(self, out, **meta: float) -> None:
        """Write it to ``out`` as one ``.npz``, whole (a scratch file beside
        it, renamed: a failure writes nothing, D35): ``bones``, ``parents``,
        ``inverse_binds``, ``sprung``, ``clips``, ``rates``, ``loops``,
        ``carried``, per clip ``i`` ``now<i>``, ``time<i>`` and
        ``worlds<i>``, and each of ``meta`` as a number."""
        import os
        import tempfile
        from pathlib import Path

        import numpy as np

        out = Path(out)
        arrays = {"bones": np.array(self.bones), "parents": np.array(self.parents, np.int32),
                  "inverse_binds": self.binds, "sprung": np.array(self.sprung, bool),
                  "clips": np.array([p.clip for p in self.clips]), "rates": np.array([p.rate for p in self.clips]),
                  "loops": np.array([p.loop for p in self.clips], bool),
                  "carried": np.array([p.carried for p in self.clips], bool)}
        for i, p in enumerate(self.clips):
            arrays |= {f"now{i}": np.array(p.now), f"time{i}": np.array(p.time), f"worlds{i}": p.worlds}
        arrays |= {k: np.array(float(v)) for k, v in meta.items()}
        out.parent.mkdir(parents=True, exist_ok=True)
        fd, part = tempfile.mkstemp(prefix=f".{out.name}.part-", dir=out.parent)
        try:
            with os.fdopen(fd, "wb") as f:
                np.savez(f, **arrays)
            os.replace(part, out)
        except BaseException:
            os.unlink(part)
            raise


def pose(springs: dict, clips=None, *, hz: int = 30, strength: float = 1.0) -> Posed:
    """Every bone's world as the game draws a build's ``springs``' body
    (``apply_player_model``'s ``springs_out``) over each of ``clips``
    (names under the body; ``None``: every slot's clip), each played as
    :func:`simulate` plays it standing (a climb loop carried, as the
    targets judge it): the engine model's world
    (:func:`~azurik_mod.assets.gltf._engine`, a carried clip's with
    :meth:`_Poser.shift` off) with X41's twin over it at
    the strength slider ``strength``: a spring row's bone moved as the
    shim writes it (its written world over the pose the twin was given),
    and every bone under it carried by that move, as the game builds a
    child from its parent's written world (Step X.65f, ``azurik-mod model
    pose``; Step 2.168's squish bones ride their breast so)."""
    import numpy as np

    from azurkit.tools.characters import gltf
    from azurkit.tools.characters.retarget import named_clip

    rows_, poser, rates = springs["rows"], _poser(springs), _rates(springs)
    info = gltf._read(springs["characters"], springs["body"])
    parents = [b.parent for b in info.bones]
    col = lambda m: np.array(m, float).reshape(4, 4).T  # noqa: E731
    sprung: list[bool] = []
    for k, p in enumerate(parents):
        sprung.append(any(r.bone == k for r in rows_) or (p >= 0 and sprung[p]))
    played, climbs = [], {springs["slots"].get(k) for k in CLIMB_LOOPS}
    for clip in sorted(set(springs["slots"].values())) if clips is None else clips:
        carried = poser.clip(clip)[2] and clip in climbs
        rate, loop, ticks = _played(springs, rates, poser, clip, hz, carried)
        source = named_clip(springs["characters"], springs["body"], clip)
        twin, frames = Twin(rows_, len(poser.rig.bones), strength), []
        for t in ticks:
            m = _qmat((0.0, 0.0, fdlibm.sin(t["yaw"] / 2.0), fdlibm.cos(t["yaw"] / 2.0)), t["origin"])
            shim = twin.pose(Pose("A", "P", "C", t["now"], t["scale"], m, t["worlds"], t["velocity"], 0,
                                  t["state"], t["rate"]))
            world, moved = gltf._engine(info, source, t["ct"]), [None] * len(parents)
            if carried:   # the twin's frame (its worlds carried)
                shift = poser.shift(clip, t["ct"])
                for w in world:
                    w[:3, 3] -= shift
            for k, p in enumerate(parents):
                if k in shim:
                    moved[k] = col(shim[k]) @ np.linalg.inv(col(t["worlds"][k]))
                elif p >= 0 and moved[p] is not None:
                    moved[k] = moved[p]
                else:
                    continue
                world[k] = moved[k] @ world[k]
            frames.append(world)
        played.append(Played(clip, rate, loop, carried, tuple(t["now"] for t in ticks),
                             tuple(t["ct"] for t in ticks), np.array(frames)))
    binds = np.array(info.binds, float).reshape(-1, 4, 4).transpose(0, 2, 1)
    return Posed(tuple(b.name for b in info.bones), tuple(parents), binds, tuple(sprung), tuple(played))


def kinds(springs: dict) -> dict[str, str]:
    """Each spring row's kind (``simulate``'s ``springs``), for
    :func:`targets`: ``bust`` or ``glutes``, a W29 row with a shape under a
    spine bone or the root (all of them: v4's two breasts and two
    glutes); ``cloth``, a ``springs`` row on a cloth chain's link
    (:data:`~azurik_mod.assets.model_chains.KINDS`), ``hem`` its last (no
    cloth row chains to it); else ``""`` (hair, a ponytail)."""
    from azurkit.tools.characters.model_chains import KINDS

    rows_, parents = springs["rows"], springs["parents"]
    placed = {pl.bone.role: pl for pl in springs.get("placed", ())}
    cloth = {r.role for r in rows_ if r.role in placed and not placed[r.role].bone.shape
             and KINDS["cloth"].search(placed[r.role].bone.bone)}
    under = {rows_[r.chain].role for r in rows_ if r.chain >= 0 and r.role in cloth}
    out = {}
    for r in rows_:
        pl = placed.get(r.role)
        if pl is not None and pl.bone.shape:
            out[r.role] = ("glutes" if 0 <= r.parent < len(parents) and parents[r.parent] < 0
                           else "bust" if "spine" in pl.bone.parent else "")
        else:
            out[r.role] = ("cloth" if r.role in under else "hem") if r.role in cloth else ""
    return out


def targets(runs30: list[Run], runs60: list[Run] | None = None, *, kinds_: dict[str, str]) -> dict[str, bool]:
    """:data:`TARGETS` judged on the runs (30 Hz; with 60 Hz's for the rate
    and chain targets), each on every row of its kind (``kinds_``,
    :func:`kinds`, required: a call without it would judge no form); a
    target with no row of its kind isn't judged."""
    by = {r.name: r for r in runs30}
    roles = list(by["idle"].peak)
    bs = [k for k in roles if kinds_.get(k) == "bust"]
    gs = [k for k in roles if kinds_.get(k) == "glutes"]
    hems = [k for k in roles if kinds_.get(k) == "hem" and k in by["run"].chain]
    ok = {}

    def land(name: str, b: str) -> float:   # a bust's largest swing in its ring from touchdown, mm
        return max((abs(e) for e in by[name].extrema[b]), default=0.0)
    if bs or gs:
        ok = {"idle": all(by["idle"].radius[k] <= 5.0 for k in bs + gs),
              "run": all(25.0 <= max(by["run"].peak[b]) <= 120.0 for b in bs)
              and all(max(by["run"].peak[g]) >= 13.0 for g in gs),
              "stop": all(30.0 <= by["stop"].peak[b][1] <= 120.0
                          and sum(abs(e) > 5.0 for e in by["stop"].extrema[b]) >= 3 for b in bs),
              "landing": (all(40.0 <= land("jump", b) <= 100.0 and by["jump"].raw[b] <= 1.1
                              and sum(abs(e) > 10.0 for e in by["jump"].extrema[b]) >= 3
                              and land("drop", b) >= 1.2 * land("jump", b) for b in bs)
                          and all(sum(abs(e) > 5.0 for e in by["jump"].extrema[g]) >= 2 for g in gs)),
              "walk": all(r.largest[k] <= 50.0 for r in runs30
                          if r.name.startswith("walk") or r.name.endswith("(loop, carried)") for k in bs + gs),
              "start": all(max(by["start"].peak[b][:2]) <= by["start"].peak[b][2] / 3.0 for b in bs)}
    if any(r.chain for r in runs30):
        ok["chain"] = (all(c["inward"] <= c["stop"] + 0.1 for r in (*runs30, *(runs60 or ())) for c in r.chain.values())
                       and all(40.0 <= by["run"].chain[h]["pp"] <= 200.0 for h in hems)
                       and all(max(map(abs, by["stop"].chain[h]["extrema"]), default=0.0) >= 20.0
                               and by["stop"].chain[h]["late"] <= by["idle"].chain[h]["reach"] + 5.0 for h in hems))
    if runs60 is not None:
        by60 = {r.name: r for r in runs60}
        ok["rate"] = (all(abs(max(by60[n].peak[k]) / max(by[n].peak[k]) - 1.0) <= 0.15
                          for n in ("run", "stop", "jump") for k in roles
                          if max(by[n].peak[k]) > 1.0 and k not in by[n].chain)
                      and all(abs(by60[n].chain[k]["pp"] / by[n].chain[k]["pp"] - 1.0) <= 0.15
                              for n in ("run", "stop", "jump") for k in by[n].chain if by[n].chain[k]["pp"] > 10.0))
    return ok


def report(runs: list[Run], judged: dict[str, bool] | None = None) -> list[str]:
    """The preview's lines: per run and row its peaks, radius, largest
    tick, ticks over 10 mm, raw over travel and ring, and a walled row's
    tip off the clip's pose; then the targets."""
    lines = ["run (hz) | row | peak mm side fwd up | radius | largest tick mm | ticks over 10 mm | raw/travel | "
             "ring mm | walled: tip mm toward her (stop), peak to peak, ring along the wall, 1.5 s on"]
    for r in runs:
        for role in r.peak:
            p, c = r.peak[role], r.chain.get(role)
            lines.append(f"{r.name} ({r.hz}) | {role} | {p[0]:.1f} {p[1]:.1f} {p[2]:.1f} | {r.radius[role]:.1f} | "
                         f"{r.largest[role]:.1f} | {r.over10[role]}/{r.ticks} | {r.raw[role]:.2f} | "
                         + " ".join(f"{e:.1f}" for e in r.extrema[role])
                         + (f" | {c['inward']:.1f} ({c['stop']:.1f}), {c['pp']:.1f}, "
                            + " ".join(f"{e:.1f}" for e in c["extrema"]) + f", {c['late']:.1f}" if c else ""))
    for key, passed in (judged or {}).items():
        lines.append(f"target {key}: {'pass' if passed else 'FAIL'} ({TARGETS[key]})")
    return lines


def spring_bones(spec) -> dict:
    """A recipe's jiggle ``spec``'s real-time springs, role ->
    :class:`Spring`: its W29 bones' and its ``springs``'."""
    return {b.role: b.spring for b in (*spec.bones, *spec.springs) if b.spring is not None}


def with_sets(variant, sets: list[str]):
    """``variant`` with each ``ROLE.FIELD=VALUE`` of ``sets`` (VALUE JSON,
    or a bare word) laid over its jiggle bones' springs, each checked as
    a recipe's (:func:`parse_spring`), and each row's spring as recipe
    JSON (role -> object, to paste); :class:`ValueError` names a set
    that isn't one."""
    import json

    if variant.jiggle is None:
        if sets:
            raise ValueError(f"--set: the variant {variant.name!r} has no jiggle")
        return variant, {}
    docs = {role: spring_json(s) for role, s in spring_bones(variant.jiggle).items()}
    for item in sets:
        key, eq, value = item.partition("=")
        role, dot, field_ = key.partition(".")
        if not eq or not dot or role not in docs:
            raise ValueError(f"--set {item!r}: ROLE.FIELD=VALUE with ROLE a spring row "
                             f"({', '.join(sorted(docs)) or 'none'})")
        try:
            docs[role][field_] = json.loads(value)
        except json.JSONDecodeError:
            docs[role][field_] = value
        if field_ == "stiffness":
            docs[role].pop("freq", None)
        if field_ == "freq":
            docs[role].pop("stiffness", None)
    new = {f: tuple(replace(b, spring=parse_spring(f"--set {b.role}", docs[b.role])) if b.role in docs else b
                    for b in getattr(variant.jiggle, f)) for f in ("bones", "springs")}
    return replace(variant, jiggle=replace(variant.jiggle, **new)), docs


__all__ = ["AIR_STATE", "BOUND", "Coeffs", "G", "GAP", "GAP_STEPS", "H", "HARD_STATE", "HEADER_SIZE", "HIT_STATE",
           "IMPACT_FALL", "KNEE", "LAND_TIME", "MAGIC", "MAX_BONES", "MAX_ROWS", "Played", "Pose", "Posed", "REST",
           "RESTITUTION", "RESTS", "ROW_SIZE", "RUN_ON", "Row", "Run", "SCENARIOS", "SHOWN_SIZE", "SPRING_KEYS",
           "SQUASH_LIMIT", "START", "SWIM_STATE", "Shown", "Spring", "TABLE_SIZE", "TARGETS", "TELEPORT", "TWO_PROBES",
           "Twin", "V0", "WALK_SPEEDS", "coefficients", "kinds", "parse_spring", "pose", "report", "rows", "simulate",
           "spring_bones", "spring_json", "spring_places", "step_matrix", "table", "targets", "with_sets"]

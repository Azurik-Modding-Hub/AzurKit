"""The weaponless townsfolk's bare-hands kit (Step 2.159a; D471, D472, D467,
D502, D474) and the borrowed attack style it is built through.

D471 (the owner): "townsfolk without weapons should not have balthazar's
beam attack or life steal. instead, they should have interesting
melee/hand attacks"; D472: new hand attacks authored with the toolkit's
Blender clip import, a jab-cross-uppercut combo, a kick and a two-hand
shove finisher.  They replace D421's lent Balthazar attacks.

- **A style** (:class:`Style`, the 2.161 design's S2): clips keyed on a
  ``source`` rig, baked onto the wearer's under ``dir``
  (``characters/<body>/<dir><clip>``, :func:`~azurik_mod.assets.retarget.bake_body`
  with that rig as its lender), the clip it plays in each column it
  takes (``picks``; the other columns keep theirs), X3's window on each
  clip (``windows``, clip seconds) and its box, X13's fill under it (the
  kit's at the limb it strikes with, ``limbs``, Step 2.195; a source
  build's his own, Step 2.195b), each clip's length, the ``Rate`` its columns play at,
  the hit effect its plain hits show and its sounds.  Worn by its own
  source family a clip bakes onto a rig with the same bone records, so
  each mapped bone turns as keyed (the bones no role maps keep their
  bind).  Since Step 2.161c a source rig's own build is this shape too
  (``own``: each column the clip his own build plays there; ``fx``, the
  species whose own-build graph the player's clone takes, W34):
  Balthazar's magic, :func:`~azurik_mod.patches._player_weapons.source_style`.
- **The kit** (``assets/clips/townsfolk/kit.json``): three rigs, one per
  townsfolk family (the townsmen's on ``male_6``, the townswomen's on
  ``female_1``, the children's on ``child_1``: every body of a family
  has the same bone records, so a clip plays exactly on each), each a
  clip-only ``.glb`` (bones and keys; game-asset snippets, D153) made by
  ``scripts/townsfolk_kit.py`` in Blender and thinned to the game's
  density, its sha256 checked as a recipe's ``gltf`` clip is; five
  clips (``jab``, ``cross``, ``upper``, ``shove``, ``kick``: their
  ticks at 30 Hz, their hit windows and the limbs each strikes with,
  ``limbs`` and ``pad``: Step 2.195, D763), the column each plays, the
  ``Rate`` 1.0 (a tick of the clip a game tick), whether X32 shows its
  small hit flash (``hit_fx``: D467's sparks, since D700 the build's
  flash, no element's) and the swing and hit sounds (D502, ``sounds``: a
  whoosh, :func:`swing_waves`, each kit column binds through X14 from the
  build's sound dir, else ``dir``; a thud, :func:`hit_wave`, X43 plays on
  the player's plain hits).
- **The throw** (Step 2.159b; D473, the owner: "Vase + rock
  (Recommended)", a second WHITE set, D325): kit.json's ``throw``, a
  :class:`Throw` on the style: the column that plays the ``throw`` clip
  (right1) throws a real projectile from the hand at its ``release``
  tick, a rock for the townsmen and children and a vase for the
  townswomen (each rig's ``throw``), :mod:`~azurik_mod.patches._player_throw`
  building it (W30) and X42 throwing it.
- **A carried prop** (:func:`carried`): a bone the bake hides (no mapped
  bone above it) that one of the wearer's own clips shows (town_female_4's
  vase, x0.4 on her head in her vaseidle and vasewalk) rides the bone it
  keeps closest to there in every kit clip and every clip of garret4's
  baked onto her (her idle, walk, roll), at that scale, so she punches
  with it on her head and it never pops in or out with an attack.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from azurkit.tools.characters.characters import Body, bone_records
from azurkit.tools.characters.retarget import Clip, Retarget, Rig, Track, named_clip, origins, origins_at

KIT = Path(__file__).resolve().parent / "clips" / "townsfolk"
"""The kit's folder: ``kit.json`` and one clip-only ``.glb`` a rig."""
KIT_FILE = KIT / "kit.json"
CARRY_HZ = 30.0
"""How often a carried prop's place is keyed (a game tick)."""
SHOWN = 1e-3
"""The least scale a stand clip shows a prop at (town_female_1's vase is keyed at 1e-12)."""


def kit_document() -> dict:
    """``kit.json`` as written (module docstring)."""
    return json.loads(KIT_FILE.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class Throw:
    """A style's throw (kit.json's ``throw``; ticks of its clip at 30 Hz):
    the ``clip`` its column plays, the projectile ``kind`` (``rock`` or
    ``vase``) and its record (``projectile``: its body's ``source``, its
    ``scale``, horizontal ``speed`` m/s and message 10's clip slot
    ``anim``), the tick it spawns in the hand at (``spawn``; a carrier's
    vase at its ``take``, the tick in that range the hand passes nearest
    the vase), leaves it at (``release``) and a carried vase comes back
    to the hand at (``back``), the swing's chain tick (``chain``: a new
    press throws again there, a held button once: D566), the aim's
    ``range``, ``miss`` distance and its height ``miss_z`` over the
    thrower's point (m), ``cone`` (degrees either side), the
    ``flight`` time's clamp (s), the hit box's ``pad`` (m), its ``life``
    (s), the ``landing`` state and the ``clear`` past the two bodies'
    radii it leaves at (m)."""

    clip: str
    kind: str
    projectile: dict
    ticks: int
    spawn: int
    take: tuple[int, int]
    release: int
    back: int
    chain: int
    range: float
    miss: float
    miss_z: float
    cone: float
    flight: tuple[float, float]
    pad: float
    life: float
    landing: int
    clear: float


@dataclass(frozen=True, eq=False)
class Style:
    """An attack style borrowed from another rig (module docstring)."""

    source: str
    """The body whose rig the clips are keyed on."""
    dir: str
    """Where they go under the wearer: ``characters/<body>/<dir><clip>``."""
    picks: dict[str, str]
    """``attacks_anims`` column -> the clip it plays (no ``dir``)."""
    windows: dict[str, tuple[float, float]]
    """Clip -> X3's window (clip seconds)."""
    lengths: dict[str, float]
    """Clip -> its length (s)."""
    rate: float | None
    """The ``Rate`` its columns play at (``None``: each column's own)."""
    load: Callable[[bytes], dict[str, Clip]] = field(repr=False)
    """The clips on the source rig, from a ``characters.xbr`` holding it."""
    hit_fx: bool = False
    """Whether its plain hits show X32's small flash (Step 2.180, D700)."""
    sounds: dict | None = None
    """Its swing and hit sounds (``kit.json``'s ``sounds``: :func:`swing_waves`, :func:`hit_wave`), or ``None``."""
    throw: Throw | None = None
    """Its throw (Step 2.159b), or ``None``."""
    own: Body | None = None
    """A source rig whose own build it plays (Step 2.161c): each column the clip that build plays there
    (``picks`` unread), else ``None``."""
    fx: str | None = None
    """The species whose own-build graph the player's clone takes (W34, Step 2.161c), else ``None``."""
    limbs: dict[str, tuple[tuple[str, ...], tuple[str, str]]] | None = None
    """Clip -> the :attr:`source` rig's bones it strikes with (the fist's hand, the kick's ankle) and the two
    whose bind distance is its pad (a fist's or a foot's length; ``kit.json``'s ``limbs``, ``pad`` and ``pads``,
    Step 2.195, D763): X3's box there is the box :func:`~azurik_mod.patches._player_character.style_windows`
    gives it, the limb's reach a fist or a foot past it; ``None``: a source build's, his own boxes (:attr:`own`,
    Step 2.195b)."""

    def clips(self, characters_xbr: bytes) -> dict[str, Clip]:
        """The style's clips keyed on :attr:`source` (by name, no ``dir``)."""
        return self.load(characters_xbr)


@functools.cache
def _kit() -> dict:
    return kit_document()


def kit_style(characters_xbr: bytes, body: Body, lend: bool = False) -> Style | None:
    """The kit as a :class:`Style` for ``body``: its family's rig (the
    one whose source's bones are the first of ``body``'s, by name and
    order: a variant's W29 bones come after), else with ``lend`` (bare
    hands picked for a body of no family, Step 2.161b) the townsmen's,
    the first, its clips baked through both role maps, else ``None``."""
    kit = _kit()
    names = [b.name for b in bone_records(characters_xbr, body.name)]
    for rig in kit["rigs"]:
        source = [b.name for b in bone_records(characters_xbr, rig["source"])]
        if names[:len(source)] == source:
            break
    else:
        if not lend:
            return None
        rig = kit["rigs"][0]
    clips = kit["clips"]
    t = kit.get("throw")
    throw = Throw(clip=t["clip"], kind=rig["throw"], projectile=dict(t["kinds"][rig["throw"]]),
                  ticks=clips[t["clip"]]["ticks"], spawn=t["spawn"], take=tuple(t["take"]), release=t["release"],
                  back=t["back"], chain=t["chain"], range=t["range"], miss=t["miss"], miss_z=t["miss_z"], cone=t["cone"],
                  flight=tuple(t["flight"]), pad=t["pad"], life=t["life"], landing=t["landing"],
                  clear=t["clear"]) if t and rig.get("throw") else None
    return Style(source=rig["source"], dir=kit["dir"], picks=dict(kit["columns"]),
                 windows={c: (p["hit"][0] / 30.0, p["hit"][1] / 30.0) for c, p in clips.items() if "hit" in p},
                 lengths={c: p["ticks"] / 30.0 for c, p in clips.items()}, rate=kit["rate"],
                 load=functools.partial(_rig_clips, rig["source"], rig["file"], rig["sha256"]),
                 hit_fx=kit["hit_fx"], sounds=kit["sounds"], throw=throw,
                 limbs={c: (tuple(p["limbs"]), tuple(kit["pads"][p["pad"]])) for c, p in clips.items() if "limbs" in p})


def _rig_clips(source: str, file: str, sha256: str, characters_xbr: bytes) -> dict[str, Clip]:
    """A rig's kit clips read onto its ``source`` body, the file's sha256
    and each clip's length checked against ``kit.json`` (D35). A read is
    kept per process by its inputs' content (the source, the file's
    sha256, the clips' ticks and what the read reads of ``characters_xbr``,
    :func:`~azurik_mod.assets.clip_import.read_key`: the source body, not
    the clips each build adds to the archive, Step X.81c), a part
    (:mod:`~azurkit.tools.characters.parts`, Step 4.6o), so each body on
    the same rig reads it once, a later visit's too; each call gets clips
    of its own (Step X.65b)."""
    import pickle

    from azurkit.tools.characters import clip_import, mesh_edit, parts

    path = KIT / file
    sha = mesh_edit.file_sha256(path) if path.is_file() else None
    if sha != sha256:
        raise ValueError(f"the townsfolk kit's {file}: its sha256 is {sha}, not kit.json's {sha256} "
                         "(scripts/townsfolk_kit.py writes both)")
    ticks = {c: p["ticks"] for c, p in _kit()["clips"].items()}
    read = clip_import.read_key(characters_xbr, source, list(ticks)) or hashlib.sha256(characters_xbr).hexdigest()
    key = parts.key("kit clips", source, sha, read, tuple(ticks.items()))
    if (kept := parts.get(key, "kit clips")) is not None:
        return pickle.loads(kept)
    out = {}
    for got in clip_import.read_clips(characters_xbr, source, path, list(ticks)):
        if abs(got.clip.length - ticks[got.name] / 30.0) > 1e-6:
            raise ValueError(f"the townsfolk kit's {file}: {got.name} lasts {got.clip.length:.4f} s, "
                             f"not kit.json's {ticks[got.name]} ticks")
        out[got.name] = got.clip
    kept = parts.dump(out)
    parts.put(key, kept, len(kept))
    return out


def swing_waves(style: Style) -> dict[str, list[int]]:
    """``style``'s swing sound (D502: a short whoosh, ``sounds.swing``)
    by leaf, each take (``<name>``, ``<name>_a`` ..) made by
    :func:`~azurik_mod.assets.synth.whoosh`; ``{}`` for a style without
    one."""
    from azurkit.tools.characters import synth

    p = (style.sounds or {}).get("swing")
    if not p:
        return {}
    return {p["name"] if take == 0 else f"{p['name']}_{chr(ord('a') + take - 1)}":
            synth.whoosh(float(p["length"]), p["swells"], p["seed"], take) for take in range(p.get("takes", 1))}


def hit_wave(style: Style) -> tuple[str, list[int]] | None:
    """``style``'s hit sound (D502: a soft thud, ``sounds.hit``): its key
    and its samples (:func:`~azurik_mod.assets.synth.thud`); ``None`` for
    a style without one."""
    from azurkit.tools.characters import synth

    p = (style.sounds or {}).get("hit")
    return (p["name"], synth.thud(float(p["length"]), p["seed"])) if p else None


def carried(characters_xbr: bytes, body: Body, source: str, stand: str | None = None
            ) -> dict[int, tuple[int, tuple[float, float, float], float]]:
    """The props a kit clip baked from ``source`` onto ``body`` carries
    (module docstring): bone -> (the bone it rides, its offset from that
    bone's origin in model axes, its scale), from the first of ``body``'s
    own clips (``stand`` first, then by name) that shows it, at that
    clip's start; ``{}`` when none shows one (town_female_1-3's vase,
    keyed at 1e-12 in every clip of theirs)."""
    rt = Retarget(characters_xbr, body.name, grow=False, lender=source)
    order = [c for c in dict.fromkeys([stand, *sorted(body.clips)]) if c in body.clips]
    out: dict[int, tuple[int, tuple[float, float, float], float]] = {}
    for name in order:
        if len(out) == len(rt.props):
            break
        clip = named_clip(characters_xbr, body.name, name)
        scales = {tr.target: tr.keys[0][1] for tr in clip.bones if tr.comp == 7}
        at = None
        for k in rt.props:
            scale = scales.get(k, rt.target.bones[k].s[0])
            if k in out or scale < SHOWN:
                continue
            at = at or origins(rt.target, clip, 0.0)
            ride = min(rt.source, key=lambda m: math.dist(at[m], at[k]))
            out[k] = (ride, tuple(a - b for a, b in zip(at[k], at[ride])), scale)
    return out


def carry(rig: Rig, clip: Clip, props: dict[int, tuple[int, tuple[float, float, float], float]]) -> Clip:
    """``clip`` with each of ``props`` (:func:`carried`) keyed on the
    bone it rides every :data:`CARRY_HZ` tick, its slope the curve's,
    at its scale: its own tracks (the bake's hidden scale) replaced."""
    if not props:
        return clip
    times = [i / CARRY_HZ for i in range(int(clip.length * CARRY_HZ + 1e-6) + 1)
             if i / CARRY_HZ < clip.length - 1e-4] + [clip.length]   # a float32 length a hair past its last tick
    n = len(times) - 1
    where = origins_at(rig, clip, times)
    tracks = [tr for tr in clip.bones if tr.target not in props]
    for k, (ride, offset, scale) in sorted(props.items()):
        for c in range(3):
            v = [w[ride][c] + offset[c] for w in where]
            keys = []
            for i, t in enumerate(times):
                lo, hi = max(0, i - 1), min(n, i + 1)
                slope = (v[hi] - v[lo]) / (times[hi] - times[lo]) if times[hi] > times[lo] else 0.0
                keys.append((t, v[i], slope, slope))
            tracks.append(Track(k, c, tuple(keys)))
        tracks += [Track(k, 7 + c, ((0.0, scale, 0.0, 0.0), (clip.length, scale, 0.0, 0.0))) for c in range(3)]
    return Clip(clip.length, tuple(sorted(tracks, key=lambda tr: (tr.target, tr.comp))), clip.markers)


__all__ = ["CARRY_HZ", "KIT", "KIT_FILE", "Style", "Throw", "carried", "carry", "hit_wave", "kit_document",
           "kit_style", "swing_waves"]

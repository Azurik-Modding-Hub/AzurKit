"""Character swaps and variants; the only package that may import numpy.

The swap is Modkit's (its ``patches/_player_*.py`` and its build-half
``assets/``, X.100), ported by ``scripts/oracle_sync.py`` (the models
family: never edit those files by hand): ``_player_character.py`` dresses
the player in a species' body (W1-W41: the body and its clips, retargeted
from garret4's where it lacks one, the sizes, the attacks and their sounds
and fx) and hooks the 40 ``player_model`` shims into ``default.xbe``
(their sources beside their prebuilt objects in ``player_model/``,
shimkit's). What it calls of Modkit's engine is ``ports.py``'s, on
AzurKit's core; ``pool.py`` runs its parallel work in the host's hands.

**The character layer** (§12.2, the plan's character group): a swap grows
``characters.xbr``, ``fx.xbr`` and ``index.xbr``, so the layer writes each
it changes whole (:data:`FILES`), all of them one group (:func:`whole_files`),
and the rest (config.xbr's cells, default.xbe's hooks and shims) as ranges,
its shims' room claimed past the packs' (``core.xbe.Carver``). It stacks
after the packs and before the Data tool's ``xbr`` operations
(``edits.layer``'s canonical order, Modkit's ``mod_apply``'s).

A recipe (:func:`normalize`) is Modkit's ``randomize-full`` flags for the
player model: ``{"species": "keylord", "mode": "own", "size": "own",
"scale": 1.0, "attack_reach": 1.0, ...}``. Its body's size folds into
player_physics' walk and roll before the packs (:func:`size`, Modkit's
``layer.size_params``), which the sdk does.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence

from azurkit.core import facts as facts_
from azurkit.core import gate
from azurkit.core.xbr.document import Document
from azurkit.edits.layer import Change, Claim, Layer, claimed, compose

TOOL = KIND = "characters"
FILES = ("gamedata/characters.xbr", "gamedata/fx.xbr", "gamedata/index/index.xbr")
"""The files the character layer writes whole, one group."""
XBE, CONFIG = "default.xbe", "gamedata/config.xbr"
READS = (XBE, CONFIG, *FILES)
"""The files a swap reads to plan (a level's too, read where it asks)."""
FIELDS = {   # a recipe's field -> (its type, apply_player_model's keyword)
    "species": (str, None), "mode": (str, "mode"), "size": (str, "size"), "scale": (float, "model_scale"),
    "attack_reach": (float, "attack_reach"), "attack_ground": (bool, "attack_ground"),
    "attack_balance": (bool, "attack_balance"), "attack_damage": (float, "attack_damage"),
    "attack_speed": (float, "attack_speed"), "anims": (str, "missing_anims"), "sounds": (str, "sounds"),
    "weapon": (str, "weapon"), "ram": (int, "ram"), "jiggle_strength": (float, "jiggle_strength"),
    "jiggle_stiffness": (float, "jiggle_stiffness")}


def normalize(given: object) -> dict:
    """``given``, a recipe's ``character``: ``species`` (a ``critters_engine``
    name) and any of :data:`FIELDS`, each of its type (a number any finite
    one, D23); unknown fields and other types refused by name."""
    if not isinstance(given, Mapping) or not isinstance(given.get("species"), str):
        raise ValueError("character: a recipe's character is an object naming its species")
    out = {}
    for name, value in given.items():
        if name not in FIELDS:
            raise ValueError(f"character: no field {name!r} (its fields: {', '.join(FIELDS)})")
        kind = FIELDS[name][0]
        ok = (isinstance(value, kind) and not isinstance(value, bool) if kind is not bool else isinstance(value, bool))
        if kind is float:
            ok = not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
            value = float(value) if ok else value
        if not ok:
            raise ValueError(f"character: {name} {value!r} is not {kind.__name__ if kind is not float else 'a finite number'}")
        out[name] = value
    return out


def whole_files(base: Mapping[str, bytes], built: Mapping[str, bytes], group: str) -> tuple[Change, ...]:
    """The character layer's whole-file group ``group``: each of
    :data:`FILES` that ``built`` holds and that differs from its vanilla
    bytes in ``base``, as one whole change, in :data:`FILES`' order.
    ``ValueError`` names a file ``built`` holds that isn't one of them."""
    if strays := sorted(set(built) - set(FILES)):
        raise ValueError(f"{group}: {', '.join(strays)} isn't a file the character layer writes whole "
                         f"({', '.join(FILES)})")
    return tuple(Change(file, 0, hashlib.sha256(base[file]).hexdigest(), bytes(built[file]), group, whole=True)
                 for file in FILES if file in built and bytes(built[file]) != base[file])


def _swap():
    from azurkit.tools.characters import _player_character as swap   # numpy's, loaded only for a swap
    return swap


def size(recipe: Mapping, vanilla) -> float:
    """The worn body's size s (garret4's height 1), as Modkit's
    ``randomize-full`` folds it into the walk and roll sliders before its
    packs: the body dressed on a scratch staging of the vanilla files
    (``vanilla``, a ``ports.Vanilla``); ``ValueError`` for a species it can't
    use."""
    from azurkit.tools.characters import ports

    swap = _swap()
    with ports.building(ports.Build(vanilla)):
        swap.check_player_model(ports.IsoStaging(vanilla), recipe["species"])
        shape = swap.size_shape(vanilla, recipe["species"], recipe.get("mode", swap.DEFAULT_MODE),
                                recipe.get("size", swap.DEFAULT_SIZE), recipe.get("anims"),
                                weapon=recipe.get("weapon"))
    return swap.movement_size(shape, recipe.get("scale", 1.0))


def _runs(old: bytes, new: bytes) -> list[tuple[int, int]]:
    """``[start, end)`` of each run where ``new`` differs from ``old`` (past ``old``'s end: all of it)."""
    out, at, n = [], None, len(new)
    for i in range(n):
        same = i < len(old) and old[i] == new[i]
        if not same and at is None:
            at = i
        elif same and at is not None:
            out.append((at, i))
            at = None
    if at is not None:
        out.append((at, n))
    return out


def plan(recipe: Mapping, vanilla, before: Sequence[Layer], packs: Mapping[str, object] = (),
         folded: float | None = None) -> tuple[Layer, list[str]]:
    """The character layer of ``recipe`` (:func:`normalize`'s) on the
    release of ``vanilla`` (a ``ports.Vanilla``), over the layers ``before``
    it (the packs: what their files hold is what the swap reads, and its
    shims take room past their claims), and the swap's build-log lines. The
    files the swap grows are one whole group; ``default.xbe``'s bytes and
    config.xbr's cells each table it changes are a group of ranges, its
    shims' placements the layer's claims. ``folded``: the size the sdk
    folded into the walk and roll, which the dressed body must have (D35).
    ``ValueError`` names why the swap can't be built."""
    from azurkit.tools.characters import ports

    swap, release = _swap(), vanilla.release
    base = {f: vanilla.read(f) for f in READS}
    taken = [(c.offset, c.size, c.writable) for la in before for c in la.claims if c.file == XBE]
    current, _ = compose(base, before)
    build = ports.Build(vanilla, taken=list(taken), packs=dict(packs))
    staging = ports.IsoStaging(vanilla, {f: bytes(b) for f, b in current.items()})
    kwargs = {FIELDS[k][1]: v for k, v in recipe.items() if k != "species"}
    attack = swap.AttackLogic()
    with ports.building(build):
        lines = swap.apply_player_model(staging, recipe["species"], logic=attack, **kwargs)
    if folded is not None and attack.size != folded:
        raise ValueError(f"character: the dressed body's size x{attack.size:.6g} isn't the x{folded:.6g} the walk "
                         "and roll were folded with")
    built = {path: bytes(buf) for path, buf in staging.changed().items()}
    if strays := sorted(set(built) - {XBE, CONFIG, *FILES}):
        raise ValueError(f"character: the swap wrote {', '.join(strays)}, which the character layer doesn't")
    who = f"player model {recipe['species']}"
    changes = list(whole_files(base, {f: built[f] for f in FILES if f in built}, f"{who} (its archives)"))
    claims = tuple(Claim(XBE, o, n, f"shim:{who}", w) for o, n, w in build.claims)
    if XBE in built:   # the bytes the swap wrote over what the packs left, its claims' header state laid down
        mine = [*before, Layer(who, TOOL, KIND, {}, (), claims)]
        reference, vanilla_claimed = bytes(compose(base, mine)[0][XBE]), claimed(base, mine)[XBE]
        changes += [Change(XBE, lo, hashlib.sha256(vanilla_claimed[lo:hi]).hexdigest(), built[XBE][lo:hi],
                           f"{who} (default.xbe)") for lo, hi in _runs(reference, built[XBE])]
    if CONFIG in built:
        tables = sorted((t.start, t.start + t.size, name) for name, t in Document(base[CONFIG]).tables.items())
        old = bytes(current.get(CONFIG, base[CONFIG]))
        for lo, hi in _runs(old, built[CONFIG]):
            table = next((name for start, end, name in tables if start <= lo < end), "config.xbr")
            changes.append(Change(CONFIG, lo, hashlib.sha256(base[CONFIG][lo:hi]).hexdigest(), built[CONFIG][lo:hi],
                                  f"{who} config/{table}"))
    layer = Layer(who, TOOL, KIND, dict(recipe), tuple(changes), claims)
    return layer, list(lines)


def packs_view(release: gate.Release, packs: Mapping[str, object]) -> dict[str, object]:
    """What the swap reads of each pack (``ports.get_pack``: the load budget's slider, the upper heaps'
    hooks), from the packs' own declarations ``packs`` (``tools.mods.PACKS``: name -> pack), its sizes
    from the release's facts."""
    from azurkit.tools.characters import ports

    facts = facts_.of(release)
    out = {}
    for name, pack in packs.items():
        sliders, hooks = [], []
        for site in pack.sites:
            kind = type(site).__name__
            if kind == "ParametricPatch" and site.va:
                with_size = facts.site(facts.va(site.va)).size
                sliders.append(ports.ParametricPatch(site.name, site.va, bytes(with_size), site.default))
            elif kind == "TrampolinePatch":
                with_size = facts.site(facts.va(site.va)).size if site.on(release.name) else 5
                hooks.append(ports.TrampolinePatch(site.shim, site.label, site.va, bytes(with_size), ports.CHECKOUT,
                                                   site.symbol, site.mode))
        out[name] = ports.PackView(name, pack.default_on, tuple(sliders), tuple(hooks))
    return out

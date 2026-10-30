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

**A variant** (Step 4.3c; Modkit's ``_player_variants``: a recipe over a
base species, its sculpted mesh, painted textures and colours, its jiggle
springs, its clips, sounds and effects) is worn as ``--player-character``
wears one: ``species`` names a built-in (``variants.json``) or one of the
recipes of the file ``variant_file`` names (``--player-variant-file``; the
files a recipe names are read beside it), its shapes sized by ``shapes``
(``{name: x}``, ``--player-shape``); an option the recipe gives must be the
variant's, and its scale and attack numbers multiply the variant's
(:func:`variant`). The layer's recipe keeps the variant's sha and its
notes the file's name, never its path (a build's manifest carries both).

**The G4 match** (Step 4.3d, P52; Modkit's ``_player_match``, which the
sync installs): :func:`match` gives the value each of Model size, Attack
reach, Attack speed and Attack damage takes for the body to stand, reach,
chain and deal damage as garret4 does, from one dress of it over the
build's packs, and its picture (:mod:`.picker`).
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from pathlib import PurePath

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
    "jiggle_stiffness": (float, "jiggle_stiffness"), "variant_file": (str, None), "shapes": (dict, None)}
VARIANT_OPTIONS = {   # a recipe's field -> _player_variants.options' keyword (Modkit's variant_options)
    "mode": "mode", "size": "size", "sounds": "sounds", "attack_balance": "balance", "attack_ground": "ground",
    "anims": "anims", "scale": "scale", "attack_reach": "reach", "attack_damage": "damage", "attack_speed": "speed",
    "jiggle_strength": "jiggle_strength", "jiggle_stiffness": "jiggle_stiffness"}


def normalize(given: object) -> dict:
    """``given``, a recipe's ``character``: ``species`` (a ``critters_engine``
    name or a variant's, :func:`variant`) and any of :data:`FIELDS`, each of
    its type (a number any finite one, D23); unknown fields and other types
    refused by name."""
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
    for shape, x in out.get("shapes", {}).items():
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            raise ValueError(f"character: shapes.{shape} {x!r} is not a finite number")
    return out


def variant(recipe: Mapping, vanilla) -> tuple[object, dict] | tuple[None, None]:
    """The variant :func:`normalize`'s ``recipe`` wears and
    ``apply_player_model``'s options for it (Modkit's ``player_variant`` and
    ``variant_options``), or ``(None, None)`` for a species: ``species`` a
    built-in variant, else one of ``variant_file``'s recipes, its shapes
    sized by ``shapes``; a mode, size, sounds, anims or on/off option the
    recipe gives must be the variant's, its scale and attack numbers
    multiply the variant's (a weapon's moveset's, under a weapon: its
    default read from ``vanilla``). ``ValueError`` (``OSError`` for the
    file) names what can't load."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import _player_weapons as weapons

    found = variants.resolve(recipe["species"], recipe.get("variant_file"))
    if found is None:
        if recipe.get("shapes"):
            raise ValueError(f"character: shapes size a variant's shapes, and {recipe['species']!r} names no variant")
        return None, None
    if recipe.get("shapes"):
        found = variants.reshaped(found, recipe["shapes"])
    weapon = recipe.get("weapon")
    default = weapons.default_name(vanilla, found) if weapon not in (None, weapons.DEFAULT, weapons.OWN) else None
    given = {VARIANT_OPTIONS[k]: v for k, v in recipe.items() if k in VARIANT_OPTIONS}
    return found, variants.options(found, weapon=weapon, default=default, **given)


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
        worn, options = variant(recipe, vanilla)
        if worn is not None:   # Modkit's randomize-full: the variant's base dressed with its recipe
            swap.check_player_model(ports.IsoStaging(vanilla), worn.base)
            shape = swap.size_shape(vanilla, worn.base, options["mode"], options["size"], None, worn,
                                    recipe.get("weapon"))
            return swap.movement_size(shape, options["model_scale"])
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


def reasons(model: str, attack, base: str | None = None) -> list[str]:
    """Why the body ``model`` (a recipe's ``species``; ``base``, a variant's
    base species) leaves a randomized build's logic unverified, by what its
    build made of its attacks and size (``attack``, an ``AttackLogic``):
    Modkit's ``layer.movement_reasons``' model half, word for word (its
    pack half is ``tools.randomizer.generator.movement_reasons``). A body no
    xemu sitting has graded (D260), none of whose idle swings is melee or
    reaches ahead of its feet, whose least attack deals under
    ``BALANCE_FLOOR`` of garret4's damage, whose attacks play at a speed of
    0 or less, or that is shorter than garret4 (X34, D356): each is a
    reason, never a refusal (D83(c))."""
    from azurkit.tools.characters._player_damage_marker import GARRET4_FORWARD

    swap, why = _swap(), []
    if model != swap.PLAYER and swap.status(base or model) == swap.UNTESTED:
        why.append(f"--player-character {model}: not yet tested as a player model (no xemu sitting has "
                   f"graded it, D260), so the logic can't count on its moves")
    who = (f"--player-character {model}" if model != swap.PLAYER
           else f"{swap.PLAYER} at its --player-character-scale and --player-attack-* values")
    if attack.reach is None:
        why.append(f"{who}: none of its idle swings (basic1, the sweeps) is melee (Step 2.61's 4 m rule), so none "
                   f"stands in for garret4's basic swing, {GARRET4_FORWARD:.2f} m ahead (D237)")
    elif attack.reach <= 0:
        why.append(f"{who}: none of its idle swings (basic1, the sweeps) reaches ahead of its feet, so no hit "
                   f"lands (X13 draws each box at or behind them at an attack reach of 0 or less)")
    if attack.damage < swap.BALANCE_FLOOR:
        why.append(f"{who}: an attack deals x{attack.damage:.2f} garret4's damage, under "
                   f"the x{swap.BALANCE_FLOOR:g} that keeps every target the logic needs killable (D223)")
    if attack.speed <= 0:
        why.append(f"{who}: --player-attack-speed {attack.speed:g} is a lock, not a speed: an attack "
                   f"played at a Rate of 0 or less never ends, so the first attack press holds the player in it")
    if attack.size < 1.0:
        why.append(f"the worn body is x{attack.size:.3g} garret4's height, so it touches pickups x{attack.size:.3g} "
                   f"his reach (X34), under the x1 the logic's proofs and its 1.5 m standing reach assume (D356)")
    return why


def plan(recipe: Mapping, vanilla, before: Sequence[Layer], packs: Mapping[str, object] = (),
         folded: float | None = None) -> tuple[Layer, list[str], list[str]]:
    """The character layer of ``recipe`` (:func:`normalize`'s) on the
    release of ``vanilla`` (a ``ports.Vanilla``), over the layers ``before``
    it (the randomizer's and the packs': what their files hold is what the
    swap reads, and its shims take room past their claims), the swap's build-log lines and the
    body's :func:`reasons` (a randomized build's). The
    files the swap grows are one whole group; ``default.xbe``'s bytes and
    config.xbr's cells each table it changes are a group of ranges, its
    shims' placements the layer's claims. ``folded``: the size the sdk
    folded into the walk and roll, which the dressed body must have (D35).
    ``ValueError`` names why the swap can't be built."""
    from azurkit.tools.characters import ports

    swap, release = _swap(), vanilla.release
    base = {f: vanilla.read(f) for f in (*READS, *sorted({c.file for la in before for c in la.changes} - {*READS}))}
    taken = [(c.offset, c.size, c.writable) for la in before for c in la.claims if c.file == XBE]
    current, _ = compose(base, before)
    build = ports.Build(vanilla, taken=list(taken), packs=dict(packs))
    staging = ports.IsoStaging(vanilla, {f: bytes(b) for f, b in current.items()})
    attack = swap.AttackLogic()
    with ports.building(build):
        worn, options = variant(recipe, vanilla)
        if worn is not None:   # Modkit's randomize-full: the base dressed with the variant's recipe
            lines = swap.apply_player_model(staging, worn.base, variant=worn, logic=attack, weapon=recipe.get("weapon"),
                                            ram=recipe.get("ram"), **options)
        else:
            kwargs = {FIELDS[k][1]: v for k, v in recipe.items() if FIELDS[k][1] is not None}
            lines = swap.apply_player_model(staging, recipe["species"], logic=attack, **kwargs)
    if worn is not None and worn.source != "built-in":   # the log names the recipe's file: its name only
        lines = [line.replace(worn.source, PurePath(worn.source).name) for line in lines]
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
    kept = {k: v for k, v in recipe.items() if k != "variant_file"} | ({"variant": worn.sha} if worn else {})
    layer = Layer(who, TOOL, KIND, kept, tuple(changes), claims)
    return layer, list(lines), reasons(recipe["species"], attack, worn.base if worn else None)


MATCHED = ("scale", "attack_reach", "attack_speed", "attack_damage")
"""The sliders a G4 button sets (Modkit's ``player_character_scale``, ``player_attack_*``)."""


def match(recipe: Mapping, vanilla, before: Sequence[Layer], packs: Mapping[str, object] = ()) -> tuple[dict, object]:
    """The G4 match of :func:`normalize`'s ``recipe`` (Modkit's
    ``garret_match``, the Player page's buttons, D358) dressed over the
    layers ``before`` it (the build's packs) on ``vanilla``'s release, and
    the staging it dressed (its files, which :mod:`.picker` draws the worn
    body from): ``{"values": {slider: value or None}, "why": {slider:
    reason}}`` for each of :data:`MATCHED` (the damage's at the recipe's
    Attack speed, a variant's each a multiplier of its recipe's), the body
    at the other sliders as set; a variant is its recipe's, unshaped, as
    Modkit's buttons read it. ``ValueError`` names why it can't dress."""
    from azurkit.tools.characters import _player_variants as variants
    from azurkit.tools.characters import ports
    from azurkit.tools.characters._player_match import garret_match

    swap = _swap()
    base = {f: vanilla.read(f) for f in (*READS, *sorted({c.file for la in before for c in la.changes} - {*READS}))}
    taken = [(c.offset, c.size, c.writable) for la in before for c in la.claims if c.file == XBE]
    current, _ = compose(base, before)
    staging = ports.IsoStaging(vanilla, {f: bytes(b) for f, b in current.items()})
    with ports.building(ports.Build(vanilla, taken=list(taken), packs=dict(packs))):
        worn = variants.resolve(recipe["species"], recipe.get("variant_file"))
        found = garret_match(staging, recipe["species"], recipe.get("mode", swap.DEFAULT_MODE),
                             recipe.get("size", swap.DEFAULT_SIZE), recipe.get("anims"), recipe.get("scale", 1.0),
                             recipe.get("attack_reach", 1.0), recipe.get("attack_balance"),
                             recipe.get("attack_ground"), worn, recipe.get("ram"))
    damage, why = found.damage(recipe.get("attack_speed", 1.0))
    names = dict(zip(("player_character_scale", "player_attack_reach", "player_attack_speed"), MATCHED))
    reasons = {names[k]: v for k, v in found.why.items() if k in names} | ({"attack_damage": why} if why else {})
    return {"values": dict(zip(MATCHED, (found.size, found.reach, found.speed, damage))), "why": reasons}, staging


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

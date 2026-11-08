"""The Variants editor's engine half (Step 4.6b; Modkit's
``authoring/variant_library.py`` past its library rules): what the
editor's tabs read of a base species from the player's image, the files
its Sounds and Colours tabs copy into a variant's folder, what a Check
says of a dress, and the Shape tab's quick preview. The sdk's
``variant_*`` calls are its only callers; a host never imports it.

- :func:`bones`: a body's bones, each ``[name, its parent's]`` (the
  Jiggle tab's springs rows name them);
- :func:`own_sounds`: the roles a base's own sounds take as the player's
  (a base with any takes no ``voice`` or ``wavs`` of a recipe's);
- :func:`kit_throw`: what a base's default weapon throws and the columns
  that throw it;
- :func:`move_sources`: the clips the Moves tab offers a body;
- :func:`laid`: what the Moves and Attacks tabs show, read-only, of a
  recipe ``from`` another;
- :func:`add_wav` and :func:`add_png`: a WAV or an edited row's PNG
  copied into a variant's folder whole, under a name a recipe takes;
- :func:`effect_bytes`: the bytes each ``effects`` row adds, as a build's
  log says;
- :func:`lists` and :func:`heard`: what the Sounds and Effects tabs offer
  (the WAV roles, the effects templates) and what a recipe's sounds and
  effects are as the loader lays them (a recipe from another's, that one's);
- :func:`moved`: the quick preview's vertices, a dress's moved to a
  recipe's other shape values on its frozen topology;
- :func:`shape_rows` and :func:`jiggle_of`: the Shape tab's sliders and
  mesh ops, and the Jiggle tab's springs, of a recipe as read.

Its arguments are the archives' bytes and the paths a host names; it
starts no thread or process and prints nothing (``tests/test_contracts.py``),
so the site's worker runs it as it is. Nothing here prints a game byte.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np


def bones(characters: bytes, body: str) -> list[list[str]]:
    """``characters/<body>``'s bones, each ``[name, its parent's]`` (``""`` for a root)."""
    from azurkit.tools.characters.body_codec import read_asset

    rig = read_asset(characters, body, vertices=False).bones
    return [[b.name, rig[b.parent].name if 0 <= b.parent < len(rig) else ""] for b in rig]


def own_sounds(files, species: str) -> tuple[str, ...]:
    """The roles ``species``' own sounds take as the player's, as its
    build binds them (``files``: config.xbr, characters.xbr, fx.xbr and
    english.xbr by their short names, :func:`~azurkit.tools.characters._player_character.model_sounds`):
    a base with any takes no ``voice`` or ``wavs`` of a recipe's, since X14
    binds every slot from one dir (the build's refusal); garret4's, none."""
    from azurkit.tools.characters._player_character import model_sounds

    return tuple(model_sounds(files, species).own)


def kit_throw(config: bytes, characters: bytes, species: str) -> tuple[str, tuple[str, ...]]:
    """What ``species``' default weapon throws as the player's and the
    attack columns that throw it (its bare-hands kit's ``rock`` or
    ``vase``), ``("", ())`` for none: X42 throws one species a build, so a
    recipe on it naming no weapon, whose own columns leave one of those,
    takes no projectile row (the build's refusal)."""
    from azurkit.tools.characters._player_kit import kit_style
    from azurkit.tools.characters._player_weapons import default_weapon
    from azurkit.tools.characters.characters import read_body
    from azurkit.tools.characters.gltf import resolve_body

    body = read_body(characters, resolve_body(characters, config, species)[0].removeprefix("characters/"))
    weapon = default_weapon(characters, body)
    style = kit_style(characters, body) if weapon is not None and weapon.style.kit is not None else None
    if style is None or style.throw is None:
        return "", ()
    return style.throw.kind, tuple(c for c, clip in style.picks.items() if clip == style.throw.clip)


@dataclass(frozen=True)
class MoveSources:
    """The clips the Moves tab offers a body: the attack columns a recipe
    may name, the body's own clips, each humanoid body's whose clips the
    bake can put on it (garret4 first, then by name; :func:`move_sources`)
    and each built-in whose own Blender clips it can lend (with the body
    they are read on)."""

    columns: tuple[str, ...]
    own: tuple[str, ...]
    lenders: dict[str, tuple[str, ...]]
    variants: dict[str, tuple[str, tuple[str, ...]]]

    def to_json(self) -> dict:
        return {"columns": list(self.columns), "own": list(self.own),
                "lenders": {k: list(v) for k, v in self.lenders.items()},
                "variants": {k: [on, list(clips)] for k, (on, clips) in self.variants.items()}}


def move_sources(config: bytes, characters: bytes, body: str, bodies: dict[str, str]) -> MoveSources:
    """:class:`MoveSources` for ``body`` (``bodies``: each species' body, to
    find a built-in's): the ``attacks_anims`` columns but the roll; a
    lender is garret4 or a body ``retarget.MAPS`` lists (D785: "Any
    humanoid body's") whose role map and ``body``'s meet
    (``retarget.Retarget``), so a body the bake doesn't serve lends nothing
    and takes nothing; a built-in lends its ``gltf`` clips without a hit
    box (a ``bake`` clip's ``variant``)."""
    from azurkit.core.xbr.nodes import named_resources, parse_toc
    from azurkit.tools.characters._player_variants import BUILTIN, PLAYER, ROLL, _builtin_clips
    from azurkit.tools.characters.ports import XbrDocument
    from azurkit.tools.characters.retarget import MAPS, TARGETS, Retarget

    columns = XbrDocument.from_bytes(config).keyed_section("attacks_anims").col_names()
    toc, clips = parse_toc(characters), {}
    for i, name in named_resources(characters).items():
        owner, _, clip = name.removeprefix("characters/").rpartition("/")
        if toc[i].tag == "banm" and name.startswith("characters/") and owner:
            clips.setdefault(owner.casefold(), []).append(clip)
    lenders = {}
    for lender in (PLAYER, *sorted(b for b in clips if b in MAPS)) if body.casefold() in TARGETS else ():
        if lender == body.casefold():
            continue
        try:
            Retarget(characters, body, grow=False, lender=lender)
        except ValueError:
            continue
        lenders[lender] = tuple(sorted(clips[lender]))
    variants, recipes = {}, json.loads(BUILTIN.read_text(encoding="utf-8"))
    for name, given in _builtin_clips().items():
        on = bodies.get(recipes[name].get("base", ""), "")
        lent = tuple(sorted(c for c, p in given.items() if p.get("generator") == "gltf" and "box" not in p))
        if lent and (on.casefold() in lenders or on.casefold() == body.casefold()):
            variants[name] = (on, lent)
    return MoveSources(tuple(c for c in columns if c != ROLL), tuple(sorted(clips.get(body.casefold(), ()))),
                       lenders, variants)


def laid(variant) -> dict:
    """What the Moves and Attacks tabs show of a recipe ``from`` another,
    read-only, as the loader lays it (Modkit's tabs read the ``Variant``):
    its ``idles``, ``slots``, ``columns`` and ``clips``, its idles' ``wait``,
    ``cancel`` (``victory_cancel``), ``drain``, ``carry`` and ``held``, and
    its ``attacks`` numbers and switches as it plays them (a weapon over
    moves of its own plays its default's, ``unarmed``: booblord's Axion
    staff; balance and ground its mode's where it gives none), with
    ``over``, the titles of that weapon and of the pick its moves make, or
    ``None``."""
    from azurkit.tools.characters._player_character import ATTACK_DEFAULTS
    from azurkit.tools.characters._player_variants import unarmed
    from azurkit.tools.characters._player_weapons import weapons

    found = weapons()
    worn = found.get(variant.weapon) if variant.columns else None
    played = unarmed(variant) if variant.columns and variant.weapon not in (None, "default", "own") else variant
    balance, ground = ATTACK_DEFAULTS.get(variant.mode, ATTACK_DEFAULTS["own"])
    pick = next((w for w in found.values() if w.style.variant == (variant.files or variant.name)), None)
    return {"idles": dict(variant.idles), "slots": dict(variant.slots), "columns": dict(variant.columns),
            "clips": json.loads(json.dumps(variant.clips)), "wait": list(variant.idle_wait),
            "cancel": variant.victory_cancel, "drain": variant.drain, "carry": list(variant.carry),
            "held": list(variant.held),
            "attacks": {"reach": played.reach, "damage": played.damage, "speed": played.speed,
                        "balance": balance if played.balance is None else played.balance,
                        "ground": ground if played.ground is None else played.ground,
                        "through_walls": played.through_walls},
            "over": None if worn is None else {"weapon": worn.title, "pick": pick.title if pick is not None else None}}


def _copy_in(folder: Path, source: Path, data: bytes, suffix: str, fallback: str) -> str:
    """``data`` (``source``'s) in ``folder`` whole under ``source``'s stem
    (its other characters ``_``; ``_2``, ``_3`` .. while another file has
    it) and ``suffix``, or the file there already holding it: its name."""
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", source.stem).lstrip("_.-") or fallback
    for n in range(1, 1000):
        name = f"{stem}{suffix}" if n == 1 else f"{stem}_{n}{suffix}"
        target = folder / name
        if not target.exists():
            break
        if target.is_file() and target.read_bytes() == data:
            return name
    else:
        raise ValueError(f"{source.name}: no free name for it in {folder}")
    folder.mkdir(parents=True, exist_ok=True)
    part = folder / f".{name}.{os.getpid()}.part"
    part.write_bytes(data)
    os.replace(part, target)
    return name


def add_wav(folder: str | Path, source: str | Path) -> str:
    """``source``, a WAV the build reads (``xbox_adpcm.read_wav``, else
    :class:`ValueError`), copied into the variant's ``folder`` whole
    (``os.replace``) under a name a recipe's ``wavs`` take (its own, its
    other characters ``_``; ``_2``, ``_3`` .. while another file has it);
    a file there already holding the same bytes is taken as it is. Its name."""
    from azurkit.tools.characters._player_variants import _WAV_FILE
    from azurkit.tools.characters.xbox_adpcm import read_wav

    source = Path(source)
    try:
        read_wav(source)
        data = source.read_bytes()
    except OSError as exc:
        raise ValueError(f"{source}: {exc.strerror or exc}") from None
    name = _copy_in(Path(folder), source, data, ".wav", "take")
    if not _WAV_FILE.match(name):
        raise ValueError(f"{source.name}: no free name for it in {folder}")
    return name


def add_png(folder: str | Path, source: str | Path, size: tuple[int, int]) -> tuple[str, str]:
    """``source``, an edited PNG of a row's texture (an 8-bit RGB or RGBA
    PNG of the texture's ``size``, (width, height), else
    :class:`ValueError`), copied into the variant's ``folder`` as
    :func:`add_wav` copies a WAV: its name and sha256, a ``png`` op's."""
    from azurkit.tools.characters.textures import read_png

    source = Path(source)
    try:
        data = source.read_bytes()
        img = read_png(data)
    except OSError as exc:
        raise ValueError(f"{source}: {exc.strerror or exc}") from None
    except ValueError as exc:
        raise ValueError(f"{source.name}: {exc}") from None
    if (img.shape[1], img.shape[0]) != tuple(size):
        raise ValueError(f"{source.name} is {img.shape[1]}x{img.shape[0]}, the row's texture {size[0]}x{size[1]} "
                         "(Export writes it at that size)")
    return _copy_in(Path(folder), source, data, ".png", "texture"), hashlib.sha256(data).hexdigest()


_ROW_BYTES = re.compile(r"its (?P<t>[a-z][a-z0-9_]*) row \(template (?P=t)@[0-9a-f]+\): .*?(?P<b>\d+) B[;)]")
"""A build log's words for an ``effects`` row: its template and the bytes it adds (its graph's, or the projectile's
copies), as ``apply_player_model`` logs them."""


def effect_bytes(log, effects) -> list[int | None]:
    """The bytes each of ``effects`` (a variant's rows, in order) adds, as
    the build ``log`` says (a template's n-th row its n-th mention), or
    ``None`` where it doesn't say."""
    said: dict[str, list[int]] = {}
    for m in _ROW_BYTES.finditer("\n".join(log)):
        said.setdefault(m["t"], []).append(int(m["b"]))
    out, seen = [], {}
    for e in effects:
        k = seen[e.template.name] = seen.get(e.template.name, -1) + 1
        got = said.get(e.template.name, [])
        out.append(got[k] if k < len(got) else None)
    return out


def lists() -> dict:
    """What the Sounds and Effects tabs offer (Modkit's Sounds and Effects
    tabs, Step 2.164b): ``roles``, the WAV roles a recipe's ``wavs`` take
    (``DROP_ROLES``), each ``takes`` files at most; ``templates``, each
    effects template's name, group, title, what it is, its engine, where it
    plays (``anchor``), its colour's default (``None``: it takes none) and
    each param's default and display range (a hint, D23) and what its
    ``auto`` takes; and ``bound_rows``, the most shields and beams a build
    plays."""
    from azurkit.tools.characters import fx_templates
    from azurkit.tools.characters._player_variants import DROP_ROLES, TAKES

    return {"roles": list(DROP_ROLES), "takes": TAKES, "bound_rows": fx_templates.BOUND_ROWS,
            "templates": [{"name": t.name, "group": t.group, "title": t.title, "what": t.what, "engine": t.engine,
                           "anchor": t.anchor, "colour": list(t.colour["default"]) if t.colour is not None else None,
                           "params": {p: {"default": spec["default"], "range": list(spec["range"]),
                                          **({"auto": spec["auto"]} if "auto" in spec else {})}
                                      for p, spec in t.params.items()}}
                          for t in fx_templates.TEMPLATES.values()]}


def effect_row(e) -> dict:
    """An ``effects`` row (:class:`~azurkit.tools.characters.fx_templates.Effect`) as a recipe writes it, its
    defaults left out."""
    t = e.template
    row: dict = {"template": t.name, "columns": list(e.columns)}
    if e.colour is not None and (t.colour is None or list(e.colour) != [float(c) for c in t.colour["default"]]):
        row["colour"] = list(e.colour)
    row |= {p: v for p, v in e.values.items() if v != t.params[p]["default"]}
    if e.seek:
        row["seek"] = True
    return row


def heard(variant) -> dict:
    """``variant``'s sounds and effects as the loader lays them (a recipe
    from another: that one's, its own ``effects`` over them): ``sounds``,
    ``voice``, ``wavs``, ``sfx``, ``shouts`` (its files), ``effects`` (each
    row as :func:`effect_row` writes it), its ``fx`` edits, ``fx_grafts``
    and ``fx_ring`` (``False``: off), and ``columns``, the attack columns
    its own clips play."""
    return {"sounds": variant.sounds, "voice": variant.voice, "wavs": {k: list(v) for k, v in variant.wavs.items()},
            "sfx": json.loads(json.dumps(variant.sfx)), "shouts": list(variant.shouts),
            "effects": [effect_row(e) for e in variant.effects], "fx": json.loads(json.dumps(variant.fx)),
            "fx_grafts": json.loads(json.dumps(variant.fx_grafts)),
            "fx_ring": False if variant.fx_ring is None else json.loads(json.dumps(variant.fx_ring)),
            "columns": sorted(variant.columns)}


FOLLOW_EDGES = 8
"""A drawn vertex the preview finds no prepared one for (a finer triangle its dress made) moves as its neighbours
do: their mean move, spread this many edges at most."""


def prepared(characters: bytes, body: str, reference, drawn: list) -> tuple:
    """What :func:`moved` keeps for ``drawn`` (each part's (positions,
    triangles) as a dress of the variant ``reference`` drew it): its
    recipe's mesh prepared on the vanilla ``characters/<body>``
    (``mesh_edit.prepare``, its dress's topology), the prepared mesh's
    positions at the reference's values and each drawn vertex's index
    among them by its position there (-1: none)."""
    from azurkit.tools.characters import mesh_edit

    folder = Path(reference.source).parent if reference.source != "built-in" else None
    ready = mesh_edit.prepare(characters, body, reference.mesh, folder)
    at = np.asarray(mesh_edit.positions(ready, reference.mesh), np.float32)
    index: dict[tuple, int] = {}
    for k, p in enumerate(map(tuple, at.tolist())):
        index.setdefault(p, k)
    return ready, at, [np.array([index.get(p, -1) for p in map(tuple, np.asarray(P, np.float32).tolist())], np.int64)
                       for P, _ in drawn]


def moved(kept: tuple, variant, drawn: list) -> list[np.ndarray]:
    """The Shape tab's quick preview (Modkit's ``variant_library.preview``):
    each of ``drawn``'s vertices moved to where the build's position steps
    put it at ``variant``'s shape values (``mesh_edit.positions`` on
    :func:`prepared`'s mesh, ``kept``), found by its position at the
    reference's; one the dress made beyond those (a finer triangle) moves
    as its neighbours do (:data:`FOLLOW_EDGES`). Approximate: the finer
    triangles the build makes at the new values aren't made (a Check
    dresses it as the build does)."""
    from azurkit.tools.characters import mesh_edit

    ready, at, found = kept
    now = np.asarray(mesh_edit.positions(ready, variant.mesh), np.float32)
    out = []
    for (P, T), k in zip(drawn, found, strict=True):
        P = np.asarray(P, np.float64)
        move, known = np.zeros_like(P), k >= 0
        move[known] = now[k[known]] - at[k[known]]
        T = np.asarray(T, np.int64).reshape(-1, 3)
        for _ in range(FOLLOW_EDGES):
            if known.all() or not len(T):
                break
            total, count = np.zeros_like(P), np.zeros(len(P))
            for a, b in ((0, 1), (1, 2), (2, 0), (1, 0), (2, 1), (0, 2)):   # each edge both ways
                src, dst = T[:, a], T[:, b]
                use = known[src] & ~known[dst]
                np.add.at(total, dst[use], move[src[use]])
                np.add.at(count, dst[use], 1)
            reached = count > 0
            move[reached] = total[reached] / count[reached, None]
            known = known | reached
        out.append(P + move)
    return out


def _sizes(shape, mesh) -> str:
    """What ``shape`` sizes, in words: each op it names (both sides of a
    mirrored one; the layers it moves, skin or cloth), the ops it sizes
    below 1 and the bones it turns out with it."""
    ops = [op for op in (mesh.ops if mesh is not None else ()) if getattr(op, "name", "") in shape.ops]
    parts = []
    for name in shape.ops:
        mine = [op for op in ops if op.name == name]
        both = any(getattr(op, "mirror", False) for op in mine)
        parts.append(name.removesuffix(" right").removesuffix(" left") + (" (both sides)" if both else "")
                     + (f", {len(mine)} layers" if len(mine) > 1 else ""))
    turns = [f"{bone.replace('_', ' ')} {abs(deg):g}° a unit over 1" for bone, _axis, deg in shape.turns]
    below = f", and below 1 {'; '.join(shape.below)} too" if shape.below else ""
    return (f"{shape.title} sizes {'; '.join(parts)}{below}" + (f", and turns out {'; '.join(turns)}" if turns else "")
            + ".")


def shape_rows(variant, recipe) -> dict:
    """The Shape tab's rows (Modkit's ``ShapeTab.load``): ``shapes``, a
    row per shape the loader reads (a recipe ``from`` another: that one's,
    the values its own), each its ``name``, ``title``, ``value``, ``sizes``
    (in words) and ``at``, the value its key is dropped at (a recipe from
    another: that one's own value, so the recipe builds as that one does
    there; else ``None``: its own shape's value is written); and ``ops``,
    its mesh's ops before its shapes sized them, each ``[name, kind, the
    shape that sizes it]``, the sized first."""
    from azurkit.tools.characters import _player_variants as variants

    parent = recipe.get("from")
    parent = variants.builtins().get(parent) if isinstance(parent, str) else None
    mesh = variant.plain or variant.mesh

    def at(shape) -> float | None:
        if "from" not in recipe:
            return None
        return next((s.value for s in (parent.shapes if parent is not None else ()) if s.name == shape.name), 1.0)

    sized = ({op: s.title for s in variant.shapes for op in s.ops}
             | {op: f"{s.title} < 1" for s in variant.shapes for op in s.below})
    ops = [[getattr(op, "name", "") or "—", type(op).__name__.removesuffix("Op").lower(),
            sized.get(getattr(op, "name", ""), "")] for op in (mesh.ops if mesh is not None else ())]
    return {"shapes": [{"name": s.name, "title": s.title, "value": s.value, "at": at(s), "sizes": _sizes(s, mesh)}
                       for s in variant.shapes],
            "ops": sorted(ops, key=lambda row: not row[2])}


def jiggle_of(variant, recipe, name: str) -> dict | None:
    """The Jiggle tab's springs: the recipe's ``jiggle`` as it builds
    (Modkit's ``JiggleTab._jiggle``), its own, or for a recipe ``from``
    another with none of its own that one's (the tab copies it into the
    recipe at its first edit); ``None`` for a variant with no jiggle."""
    from azurkit.tools.characters import _player_variants as variants

    if variant.jiggle is None:
        return None
    if "from" in recipe and not isinstance(recipe.get("jiggle"), dict):
        laid = variants.recipe_of({name: dict(recipe)}, name, "editor")[0].get("jiggle")
        return laid if isinstance(laid, dict) else None
    return recipe["jiggle"] if isinstance(recipe.get("jiggle"), dict) else None


__all__ = ["FOLLOW_EDGES", "MoveSources", "add_png", "add_wav", "bones", "effect_bytes", "jiggle_of", "kit_throw",
           "move_sources", "moved", "own_sounds", "prepared", "shape_rows"]

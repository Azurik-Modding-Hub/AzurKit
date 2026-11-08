"""The Variants editor's pictures of a recipe's ``colours`` (Modkit's
``authoring/colour_preview.py``, Step 2.164c; D539, D768, D772), moved
into the shipped package so the editor needs nothing of Modkit's
authoring side: its body drawn front and back by
:func:`~azurkit.tools.characters.draw.draw_batched` (numpy, no Blender),
each material row's texture recoloured as W38 recolours it
(:func:`~azurkit.tools.characters.paint.recoloured`: an entry with no
``row`` every row's ops, then a named row's own; a row no entry names that
draws a named row's texture follows the last such row, as
``paint.write_colours`` does), sampled at most :data:`TEXTURE_MAX` texels
across, which a :data:`SIZE` px view can't tell from the whole texture.

:class:`Base` is the body before its colours: the base species' own body
in the player's image (:func:`vanilla`), or for a recipe whose build
changes the body (:func:`dresses`) the body its build dresses (the sdk's
Check), a prop on a bone root of its own left out (:func:`props`: the
townswomen's vase, which the player's clips hold at zero size). A row's
tile and its palette (:func:`palette`, its main colours; :func:`swatches`,
the tab's, before its ops and after) are recoloured at once while a slider
moves; :func:`views` draws the two pictures.

The PNG round trip (Step 2.203, D544): :func:`rows` is each row's texture
whole as the variant's build recolours it, which :func:`pngs` names
``<name>_row<R>.png``; an edited one comes back as the row's ``png`` op
(:mod:`~azurkit.tools.characters.paint`). It writes no built byte, yet
its own sines and cosines are ``core/fdlibm.py``'s like the swap's (so it
needs no place in ``tests/test_contracts.py``'s ``SAME_BITS_ASIDE``; the
drawing it calls is ``draw.py``'s, which keeps numpy's), and it reads and
writes no file: the sdk hands it the archives and writes what it gives. Modkit's ``keep`` and ``kept`` (a
dress pickled for the GUI's previews) are left out: AzurKit's store keeps
no pickle. Nothing here prints a game byte.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace

import numpy as np

from azurkit.core import fdlibm
from azurkit.tools.characters import draw, paint

TEXTURE_MAX = 256
"""A texture's longest side as the views sample it (every k-th texel)."""
SIZE = 160
"""Each view's side, px (the picker's picture)."""
TILE = 64
"""A row's tile, px."""
COLOURS = 6
"""A row's palette: its main colours."""
YAWS = {"front": draw.PREVIEW_VIEW[0], "back": draw.PREVIEW_VIEW[0] - 180.0}
"""Each view's yaw: the picker's, and the same from behind."""


@dataclass
class Base:
    """A body as the views draw it before its colours: ``parts`` (each
    with ``raw``, its texture as stored, every k-th texel, RGBA uint8),
    the ``body`` it is, whether a build ``dressed`` it, each row's
    texture's size as stored, ``sizes`` {row: (width, height)} (a ``png``
    op's image is that size), and whether it is a ``preview``, another
    dress's vertices moved to its shape values (:meth:`moved`)."""

    body: str
    parts: list
    dressed: bool
    sizes: dict = field(default_factory=dict)
    preview: bool = False

    def moved(self, positions: list) -> Base:
        """This body with each part's vertices at ``positions`` (its textures shared): a preview."""
        parts = []
        for q, p in zip(self.parts, positions, strict=True):
            q = copy.copy(q)
            q.P = p
            parts.append(q)
        return Base(self.body, parts, self.dressed, self.sizes, True)

    def rows(self) -> dict[int, np.ndarray]:
        """Each material row the body draws (LOD 0) with a texture, and its texture as sampled."""
        out: dict[int, np.ndarray] = {}
        for q in sorted(self.parts, key=lambda q: q.row):
            if q.surf is not None:
                out.setdefault(q.row, q.raw)
        return out


def dresses(variant) -> bool:
    """Whether ``variant``'s build changes its body's mesh or textures (so
    its views need the dressed body): a ``mesh``, ``textures`` or a
    ``texture_scale``."""
    return variant.mesh is not None or bool(variant.textures) or variant.texture_scale != 1


def uncoloured(variant):
    """``variant`` as the body its views recolour is dressed: a recipe on
    garret4's own body without its ``colours`` (his build recolours his own
    rows in place, so they would be recoloured twice), any other as it is
    (W38 recolours a copy, its body's rows untouched)."""
    from azurkit.tools.characters._player_variants import PLAYER

    return replace(variant, colours=()) if variant.base == PLAYER and variant.colours else variant


def _sampled(raw: np.ndarray) -> np.ndarray:
    k = -(-max(raw.shape[:2]) // TEXTURE_MAX)
    return np.ascontiguousarray(raw[::k, ::k])


def _texture(raw: np.ndarray, boost: bool) -> np.ndarray:
    tex = raw.astype(np.float64) / 255
    if boost:
        tex[:, :, :3] = np.clip(tex[:, :, :3] * draw.BOOST, 0, 1)
    return tex


def props(characters: bytes, body: str) -> set[int]:
    """The LOD-0 groups of ``characters/<body>`` weighted only to bones under
    a root other than the body's own (the root most of its vertices hang
    from): a prop the game moves on its own, such as the townswomen's
    ``vase_joint`` vase, which every clip the player plays holds at zero
    size, or garret4's staff."""
    from azurkit.tools.characters import body_codec
    from azurkit.tools.characters.characters import bone_records

    parents = [b.parent for b in bone_records(characters, body)]

    def root(b: int) -> int:
        while parents[b] >= 0:
            b = parents[b]
        return b
    roots = []
    for g in body_codec.read_asset(characters, body).lods[0].groups:
        weighted: dict[int, int] = {}
        for v in range(len(g.vertices)):
            for b in g.skin(v):
                weighted[root(b)] = weighted.get(root(b), 0) + 1
        roots.append(weighted)
    total: dict[int, int] = {}
    for weighted in roots:
        for r, n in weighted.items():
            total[r] = total.get(r, 0) + n
    own = max(total, key=lambda r: (total[r], -r)) if total else None
    return {k for k, weighted in enumerate(roots) if weighted and own not in weighted}


def base(characters: bytes, body: str, dressed: bool = False) -> Base:
    """``characters/<body>`` of ``characters`` (a characters.xbr) as a :class:`Base`."""
    from azurkit.core.xbr.nodes import parse_toc
    from azurkit.tools.characters import render
    from azurkit.tools.characters.characters import body_at

    toc = parse_toc(characters)
    index, _ = body_at(characters, body)
    parts, raws, sizes = draw.body_parts(characters, toc, index, props(characters, body)), {}, {}
    for q in sorted(parts, key=lambda q: q.row):
        if q.surf is not None and q.surf not in raws:
            img = render.surf_image(characters, toc, q.surf)
            raws[q.surf] = _sampled(img), (img.shape[1], img.shape[0])
        if q.surf is not None:
            sizes.setdefault(q.row, raws[q.surf][1])
        q.raw = raws[q.surf][0] if q.surf is not None else np.full((1, 1, 4), 255, np.uint8)
        q.tex = _texture(q.raw, q.boost)
    return Base(body, parts, dressed, sizes)


def body_of(config: bytes, characters: bytes, species: str) -> str:
    """The body ``species`` (or a body's own name) wears, ``characters/`` left off."""
    from azurkit.tools.characters.gltf import resolve_body

    return resolve_body(characters, config, species)[0].removeprefix("characters/")


def vanilla(config: bytes, characters: bytes, species: str) -> Base:
    """``species``' own body, as the player's image's ``config`` and ``characters`` (config.xbr, characters.xbr) hold it."""
    return base(characters, body_of(config, characters, species))


def specs(colours, folder=None) -> tuple:
    """A recipe's ``colours`` (as written) as the loader reads them
    (:class:`~azurkit.tools.characters.paint.ColourSpec`), each ``png`` op's
    file in ``folder`` (the recipe's, :func:`~azurkit.tools.characters.paint.located`);
    :class:`ValueError` names what it refuses."""
    from azurkit.tools.characters._player_variants import _colours

    return paint.located(_colours("colours", colours), folder) if colours else ()


def ops_by_row(base_: Base, colours: tuple) -> dict[int, tuple]:
    """Each row's ops under ``colours`` (:class:`~azurkit.tools.characters.paint.ColourSpec` s), as W38 lays them."""
    named = {s.row: s.ops for s in colours if s.row is not None}
    every = tuple(op for s in colours if s.row is None for op in s.ops)
    leads = {}
    for q in sorted(base_.parts, key=lambda q: q.row):
        if q.row in named and q.surf is not None:
            leads[q.surf] = q.row
    return {q.row: every + named.get(q.row, named.get(leads.get(q.surf), ())) for q in base_.parts}


def recoloured(base_: Base, colours: tuple) -> list:
    """``base_``'s parts with their textures recoloured by ``colours``."""
    by_row, done, out = ops_by_row(base_, colours), {}, []
    for q in base_.parts:
        ops = by_row.get(q.row, ())
        if not ops or q.surf is None:
            out.append(q)
            continue
        key = (q.surf, repr(ops))
        if key not in done:
            done[key] = paint.recoloured(q.raw, ops)
        part = copy.copy(q)
        part.tex = _texture(done[key], q.boost)
        out.append(part)
    return out


def rows(characters: bytes, body: str, colours: tuple) -> dict[int, np.ndarray]:
    """Each material row ``characters/<body>`` of ``characters`` (the
    vanilla archive, or for a recipe whose build changes the body,
    :func:`dresses`, the one its build dresses before its colours,
    :func:`uncoloured`) draws at LOD 0 with a texture (a prop's too:
    :func:`props` is the views' rule): the texture's base level (an
    animated list's first frame) whole, recoloured by ``colours``
    (:func:`specs`, located) as its build recolours them."""
    from types import SimpleNamespace

    from azurkit.core.xbr.nodes import parse_toc
    from azurkit.tools.characters import render

    toc, surfs = parse_toc(characters), {}
    for gshd, row in sorted(set(paint.materials(characters, body).values()), key=lambda m: (m[1], m[0])):
        stages = render.material(characters, toc, gshd, row).get("textures", [])
        if stages:
            surfs.setdefault(row, stages[0])
    by_row = ops_by_row(Base(body, [SimpleNamespace(row=r, surf=s) for r, s in surfs.items()], False), colours)
    return {r: paint.recoloured(render.surf_image(characters, toc, s), by_row.get(r, ())) for r, s in surfs.items()}


def pngs(name: str, rows_: dict[int, np.ndarray]) -> dict[str, bytes]:
    """``rows_`` (:func:`rows`') as the files the Colours tab's Export
    writes: ``{"<name>_row<R>.png": PNG bytes}``, in row order."""
    return {f"{name}_row{r}.png": draw.png_rgba(rows_[r], 6) for r in sorted(rows_)}


def views(parts: list, size: int = SIZE) -> dict[str, np.ndarray]:
    """``parts`` drawn from the front and from behind: {view: (size, size, 4) RGBA uint8}."""
    return {name: draw.draw_batched(parts, yaw, size, draw.PREVIEW_VIEW[1]) for name, yaw in YAWS.items()}


def pictures(parts: list, size: int = SIZE) -> dict[str, bytes]:
    """:func:`views` as PNG bytes, ``{"front", "back"}`` (the picker's pictures' form)."""
    return {name: draw.png_rgba(img, 6) for name, img in views(parts, size).items()}


def across(parts: list) -> float:
    """How wide ``parts`` draw in :func:`views` against how tall (the
    wider view's; 1 at most, as a view fits the body's longer side to its
    own): a standing body fills that much of a view's width about its
    middle, so the editor crops its views to a portrait that wide and
    draws them larger in the same room."""
    points = np.concatenate([q.P for q in parts if len(q.T)])
    pitch, out = float(np.radians(draw.PREVIEW_VIEW[1])), 0.0
    for yaw in map(float, np.radians(list(YAWS.values()))):    # _View's camera axes
        right = np.array((fdlibm.cos(yaw), fdlibm.sin(yaw), 0.0))
        look = (np.array((-fdlibm.sin(yaw), fdlibm.cos(yaw), 0.0)) * fdlibm.cos(pitch)
                - np.array((0.0, 0.0, 1.0)) * fdlibm.sin(pitch))
        wide, tall = np.ptp(points @ right), np.ptp(points @ np.cross(right, look))
        out = max(out, float(wide / max(wide, tall, 1e-9)))
    return out


def portrait(size: int, share: float) -> int:
    """The width, px, of a ``size`` px view cropped about its middle to a
    body :func:`across` gives ``share``: the body's (``size`` less the
    view's 1 px margins, times ``share``), its outline and a pixel each
    side (``size`` at most)."""
    return min(size, int(np.ceil(share * (size - 2))) + 4)


def tile(raw: np.ndarray, size: int = TILE) -> np.ndarray:
    """A row's texture as a ``size`` px square tile (its nearest texels, opaque)."""
    h, w = raw.shape[:2]
    at = (np.arange(size) + 0.5) / size
    out = raw[(at * h).astype(np.int64)][:, (at * w).astype(np.int64)].copy()
    out[..., 3] = 255
    return out


def palette(raw: np.ndarray, count: int = COLOURS) -> np.ndarray:
    """A texture's ``count`` main colours (RGB uint8, the most texels'
    first): k-means of its opaque texels, seeded at their brightness'
    quantiles, the same each time."""
    px = raw.reshape(-1, 4)
    px = px[px[:, 3] >= 128][:, :3].astype(np.float64)
    if not len(px):
        px = raw.reshape(-1, 4)[:, :3].astype(np.float64)
    px = px[:: max(1, len(px) // 4096)]
    order = np.argsort(px.sum(1), kind="stable")
    centres = px[order[((np.arange(count) + 0.5) * len(px) / count).astype(int)]]
    for _ in range(8):
        apart = px[:, None, :] - centres[None]
        near = (apart * apart).sum(-1).argmin(1)
        for c in range(count):
            if (near == c).any():
                centres[c] = px[near == c].mean(0)
    sizes = np.bincount(near, minlength=count)
    return np.round(centres[np.argsort(-sizes, kind="stable")]).astype(np.uint8)


def swatches(base_: Base, colours: tuple, row: int | None) -> tuple[np.ndarray, np.ndarray]:
    """The Colours tab's palette of ``row`` (``None``: every row, and the
    ops of an entry with no ``row``): its main colours as ``colours``'
    ``png`` ops leave them (:func:`palette` of its texture, every row's
    together), and the same colours after the ops past the last ``png``
    op, one for one (RGB uint8 each): where the wheel's ``hsv`` op and a
    swap take each."""
    rows_ = base_.rows()
    ops = ops_by_row(base_, colours).get(row, ()) if row is not None else tuple(
        op for s in colours if s.row is None for op in s.ops)
    cut = max((k + 1 for k, op in enumerate(ops) if op.op == "png"), default=0)   # a png's palette is its own
    raws = [rows_[row]] if row in rows_ else list(rows_.values())
    if not raws:
        return np.zeros((0, 3), np.uint8), np.zeros((0, 3), np.uint8)
    found = palette(np.concatenate([paint.recoloured(r, ops[:cut]).reshape(-1, 4) for r in raws])[:, None])
    opaque = np.concatenate([found, np.full((len(found), 1), 255, np.uint8)], 1)[None]
    return found, paint.recoloured(opaque, ops[cut:])[0, :, :3]


__all__ = ["COLOURS", "SIZE", "TEXTURE_MAX", "TILE", "YAWS", "Base", "across", "base", "body_of", "dresses",
           "ops_by_row", "palette", "pictures", "portrait", "props", "recoloured", "rows", "pngs", "specs", "swatches",
           "tile", "uncoloured", "vanilla", "views"]

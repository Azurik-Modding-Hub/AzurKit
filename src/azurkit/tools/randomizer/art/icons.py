#!/usr/bin/env python3
"""The icon sheet of the tracker and the Randomizer's lists, one picture: the
game's own 2D menu art where it has some, its 3D models where it has none.

:data:`MENU_ART` is interface.xbr's status screen: each of the 20 disc
fragments, the 4 gems, the obsidian, each placed key's picture (its medallion,
the lower half, which reads at a list's size) and the 4 element orbs (cut from
the status screen's buttons).  The other items have no 2D art: each
(:data:`ICONS`) is a model drawn with its own textures
(``azurik_mod/xbr/draw.py``): an item's character body (characters.xbr, the
``critters_engine`` body config.xbr names), or a barrier's platform meshes as
a level places them, seen in a 3/4 view under one light on a transparent
ground, at ``SS`` times the size and box-filtered down.  An opaque part is cut
out where its texture's alpha is under its material's reference, as the game
draws it.  The fire barrier is particles with no mesh, so the page's drawn
flame stays and it has no tile; the smash wall, a faint glow plane, is drawn
here (:data:`DRAWN`).  The fuel's sphere wears fx.xbr's chroma field, the
colours the game puts on the chromatic fuel, mapped by the surface's facing
(D203).  :func:`sheet` lays them out; :func:`css` names each tile for the
page's lists.
"""

from __future__ import annotations

import numpy as np

from azurkit.tools.randomizer.art.draw import OUTLINE, PITCH, SS, Part, dot, down, draw

TILE, COLUMNS = 40, 8   # a tile's pixels (sharp at a list's 18 px on a Retina screen, the map's 20) and the sheet's width
# The status screen's 4 element orbs in status/buttons: x0, y0, x1, y1.
ORBS = {"power_earth": (106, 18, 149, 63), "power_water": (52, 68, 95, 111),
        "power_fire": (160, 69, 202, 112), "power_air": (106, 125, 148, 168)}
MEDALLION = (0, 64, 64, 128)    # a status/key_<fourcc>'s lower half
SOLID = 128                     # the alpha a picture's own shape holds
# icon: (source, yaw in degrees); a source is ("body", <characters.xbr body>)
# or ("barrier", <level>, <its id in the level's generated file>): the items
# and barriers with no 2D art.
ICONS = {
    "power_life": (("body", "power_life"), 30), "power_ammo": (("body", "power_ammo"), 30),
    "power_staff1": (("body", "power_staff1"), 30), "power_staff2": (("body", "power_staff2"), 30),
    "fuel": (("body", "large_chromatic_fuel"), 30), "health": (("body", "large_health"), 30),
    "large_air_fuel": (("body", "large_air_fuel"), 30), "large_earth_fuel": (("body", "large_earth_fuel"), 30),
    "large_fire_fuel": (("body", "large_fire_fuel"), 30), "large_water_fuel": (("body", "large_water_fuel"), 30),
    "crystal": (("barrier", "e5", "e5/g0/r2304"), 30),
    "ice_block": (("barrier", "w1", "w1/g0/r1433"), 35),
    "acid_block": (("barrier", "a1", "a1/g0/r2356"), 35),
}
# D193 (Step 2.53): the icons weak at 20 px, tuned, still drawn from their
# models: "colours" multiplies in a barrier's vertex colours (each mesh's
# mean, the model's own colour) as the game does (MODULATE2X: twice), "gain"
# brightens, "roll" turns the view in the picture's plane (a long model
# across the diagonal) and "rim" is the rim's colour.  D203 (Step 2.57,
# the owner's pick): the fuel wearing a ``skin`` (an XBR's image, its colour
# times a factor).  Step 2.84
# (D193's rest): the two staff powers, the darkest on the maps' disc,
# brightened, the thin second one also turned across the diagonal.
LOOKS = {
    "power_staff1": {"gain": 2.0},
    "power_staff2": {"gain": 3.0, "roll": 45.0},
    "acid_block": {"colours": True, "gain": 3.0},
    "ice_block": {"colours": True},
    "crystal": {"colours": True, "gain": 12.0, "rim": (190, 196, 204)},
    "fuel": {"skin": ("gamedata/fx.xbr", "fx/jdtchromafield_000.tif", 2.0)},
}


# --------------------------------------------------------------------------- models
def body_parts(rd, cache: dict, body: str) -> list[Part]:
    """A character body's parts (characters.xbr, read once into ``cache``)."""
    from azurkit.tools.randomizer.art import render
    from azurkit.core.xbr.nodes import named_resources, parse_toc

    if "characters" not in cache:
        cache["characters"] = bytes(rd.read_file("gamedata/characters.xbr"))
    data = cache["characters"]
    toc = parse_toc(data)
    index = next(i for i, n in named_resources(data).items() if n.lower() == f"characters/{body}".lower())
    return [Part(data, toc, me) for me in render.body_meshes(data, toc, index)]


def barrier_parts(rd, schema, level: str, bid: str, colours: bool = False) -> list[Part]:
    """Every shape of the barrier ``bid`` (the level's generated file), as placed."""
    import json

    from azurkit.tools.randomizer.levels import GENERATED
    from azurkit.tools.randomizer.art import nodes, render
    from azurkit.core.xbr.nodes import parse_toc

    gen = json.loads((GENERATED / f"{level}.json").read_text(encoding="utf-8"))
    shapes = next(b["shapes"] for b in gen["barriers"] if b["id"] == bid)
    data = bytes(rd.read_file(f"gamedata/{level}.xbr"))
    toc, graphs = parse_toc(data), nodes.graphs(data, schema)
    parts = []
    for gid in shapes:
        _, g, r = gid.split("/")
        graph, i = graphs[int(g[1:])], int(r[1:])
        parts += [Part(data, toc, render.mesh(data, toc, *b), graph.world(i)[0], colours)
                  for b in render.platform_bindings(graph, i)]
    return parts


def smash_wall(size: int) -> np.ndarray:
    """The smash wall's icon, drawn (AZ-463): f1's and w3's walls are faint
    glow planes, near-invisible at 20 px, so, as the fire barrier's flame,
    a stone wall of four courses split top to bottom by a dark crack."""
    n = size * SS
    y, x = (np.mgrid[0:n, 0:n] + 0.5) / n
    inside = (np.abs(x - 0.5) < 0.42) & (np.abs(y - 0.5) < 0.4)
    rows = (y - 0.1) / 0.8 * 4
    course = np.floor(rows)
    bricks = (x - 0.08) / 0.84 * 2 + 0.5 * (course % 2)
    mortar = (np.abs(rows - np.round(rows)) < 0.07) | (np.abs(bricks - np.round(bricks)) < 0.05)
    crack = np.array(((0.56, 0.06), (0.44, 0.34), (0.6, 0.58), (0.42, 0.94)))
    near = np.full(x.shape, np.inf)
    for (ax, ay), (bx, by) in zip(crack[:-1], crack[1:]):
        t = np.clip(((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / ((bx - ax) ** 2 + (by - ay) ** 2), 0, 1)
        near = np.minimum(near, np.hypot(x - ax - t * (bx - ax), y - ay - t * (by - ay)))
    stone = np.array((196, 168, 132)) / 255 * (1.0 - 0.06 * (course % 2))[:, :, None]
    rgb = np.where(mortar[:, :, None], np.array((110, 96, 80)) / 255, stone)
    rgb = np.where((near < 0.045)[:, :, None], np.array(OUTLINE) / 255, rgb)
    return down(rgb, inside.astype(np.float64), size)


DRAWN = {"smash_wall": smash_wall}     # icons drawn for the GUI, no model showing at 20 px


def fourccs() -> dict[str, str]:
    """Each key the vanilla data places (R1.1's generated files) and its
    fourcc, which names its status picture as the game names it (the XBE's
    ``key_xxxx``)."""
    import json

    from azurkit.tools.randomizer.levels import GENERATED

    docs = [json.loads(path.read_text(encoding="utf-8")) for path in GENERATED.glob("*.json")]
    fourcc = {k["key_type"]: k["key_fourcc"] for doc in docs for k in doc.get("keylocks", ()) if k.get("key_type")}
    return {item: fourcc[item] for item in sorted({loc["item"] for doc in docs for loc in doc["locations"]
                                                   if loc["item"].startswith("key_")})}


def menu_art() -> dict[str, tuple[str, tuple[int, int, int, int] | None]]:
    """The icons with the game's 2D art: each one's interface.xbr picture and the box of it shown (None: all of it)."""
    return {**{f"frag_{e}_{i}": (f"status/{e}frag{i}", None)
               for e in ("air", "water", "fire", "earth", "life") for i in (1, 2, 3, 4)},
            **{f"gem_{g}": (f"status/{g}", None) for g in ("diamond", "emerald", "ruby", "sapphire")},
            "obsidian": ("status/obsidian", None),
            **{k: ("status/buttons", box) for k, box in ORBS.items()},
            **{k: (f"status/key_{f}", MEDALLION) for k, f in fourccs().items()}}


def orb(a: np.ndarray) -> np.ndarray:
    """A box cut round an orb with its corners, the buttons' other parts, clear."""
    h, w = a.shape[:2]
    y, x = np.mgrid[0:h, 0:w] + 0.5
    out = a.copy()
    out[(2 * x / w - 1) ** 2 + (2 * y / h - 1) ** 2 > 1, 3] = 0
    return out


def names() -> list[str]:
    """The sheet's icons, in its order."""
    return sorted([*menu_art(), *ICONS, *DRAWN])


def _box(a: np.ndarray, n: int, axis: int) -> np.ndarray:
    """``a`` (integers) box-filtered to ``n`` along ``axis``, ``m`` times over: each new pixel the sum of the old ones
    it covers, each weighed by how much, in ``1 / m`` of a new pixel (so the weights sum to ``m``). Integers, so
    exact in any order: float sums are BLAS's, rounded in its kernel's order, which differs by chip and macOS, so a
    mean on a tie (x.5) rounded either way and GitHub's M1 drew another sheet (Step 4.4ci8)."""
    m = a.shape[axis]
    old, new = np.arange(m), np.arange(n)[:, None]
    cover = np.minimum((old + 1) * n, (new + 1) * m) - np.maximum(old * n, new * m)
    return np.moveaxis(np.tensordot(np.clip(cover, 0, None), a, axes=(1, axis)), 0, axis)


def fit(a: np.ndarray, size: int) -> np.ndarray:
    """An RGBA picture's solid part (past :data:`SOLID`: two life fragments' and two keys' pictures hold a faint stray
    ring), its shape kept, in the middle of a transparent ``size`` px square, weighted by its alpha as it shrinks
    (each new pixel's alpha the mean of what it covers, its colour their alpha-weighted mean, each rounded half up,
    exactly): (size, size, 4) RGBA uint8."""
    ys, xs = np.nonzero(a[:, :, 3] > SOLID)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.int64)
    a[:, :, :3] *= a[:, :, 3:]
    h, w = a.shape[:2]
    nh, nw = max(1, round(h * size / max(h, w))), max(1, round(w * size / max(h, w)))
    a = _box(_box(a, nh, 0), nw, 1)
    colour, alpha = a[:, :, :3], a[:, :, 3:]
    out = np.zeros((size, size, 4), np.uint8)
    y, x = (size - nh) // 2, (size - nw) // 2
    out[y:y + nh, x:x + nw, :3] = np.where(alpha > 0, (2 * colour + alpha) // np.maximum(2 * alpha, 1), 0)
    out[y:y + nh, x:x + nw, 3:] = (2 * alpha + h * w) // (2 * h * w)
    return out


def icon(rd, schema, cache: dict, name: str, size: int = TILE) -> np.ndarray:
    """``ICONS[name]`` or ``DRAWN[name]``, drawn with its ``LOOKS``: (size, size, 4) RGBA uint8."""
    if name in DRAWN:
        return DRAWN[name](size)
    (src, yaw), look = ICONS[name], dict(LOOKS.get(name, {}))
    colours, skin = look.pop("colours", False), look.pop("skin", None)
    parts = body_parts(rd, cache, src[1]) if src[0] == "body" else barrier_parts(rd, schema, *src[1:], colours)
    if skin:
        parts = skinned(rd, parts, *skin, yaw, look.get("pitch", PITCH))
    return draw(parts, yaw, size, **look)


def sheet(rd, schema) -> tuple[np.ndarray, dict]:
    """The sheet (RGBA) and where its tiles are (``{"tile": px, "columns": n, "names": [icon]}``: the icon at index i
    in row i // n, column i % n): every icon :func:`names` gives."""
    from azurkit.core.xbr.nodes import named_resources, parse_toc
    from azurkit.tools.randomizer.art import render

    data = bytes(rd.read_file("gamedata/interface.xbr"))
    toc, index = parse_toc(data), {n: i for i, n in named_resources(data).items()}
    flat, cache, all_names = menu_art(), {}, names()
    out = np.zeros(((len(all_names) + COLUMNS - 1) // COLUMNS * TILE, COLUMNS * TILE, 4), np.uint8)
    for i, name in enumerate(all_names):
        if name in flat:
            picture, box = flat[name]
            image = render.surf_image(data, toc, index[f"interface/{picture}.tif"])
            image = image if box is None else image[box[1]:box[3], box[0]:box[2]]
            tile = fit(orb(image) if name in ORBS else image, TILE)
        else:
            tile = icon(rd, schema, cache, name)
        out[i // COLUMNS * TILE:(i // COLUMNS + 1) * TILE, i % COLUMNS * TILE:(i % COLUMNS + 1) * TILE] = tile
    return out, {"tile": TILE, "columns": COLUMNS, "names": all_names}


def css(version: str, tiles: dict) -> str:
    """``art/icons.css``, which needs no script, so a list's icons show before the maps' index is read: ``.glyph`` wears
    the sheet in steps of its ``--g`` (app.css), and ``.glyph.<icon>`` shows that icon's tile."""
    n = tiles["columns"]
    lines = [f".glyph {{ background: url({version}/icons.png) no-repeat; background-size: calc(var(--g) * {n}) auto; }}"]
    lines += [f".glyph.{name} {{ background-position: calc(var(--g) * {-(i % n)}) calc(var(--g) * {-(i // n)}); }}"
              for i, name in enumerate(tiles["names"])]
    return "\n".join(lines) + "\n"


def skinned(rd, parts: list[Part], xbr: str, image: str, colour: float, yaw: float, pitch: float) -> list[Part]:
    """``parts`` (glow sprites left out) wearing ``xbr``'s ``image``, opaque,
    its colour's distance from grey times ``colour``, mapped by each point's
    facing from the model's centre as seen from ``yaw``/``pitch`` (a sphere
    map)."""
    from azurkit.tools.randomizer.art import render
    from azurkit.core.xbr.nodes import named_resources, parse_toc

    data = bytes(rd.read_file(xbr))
    index = next(i for i, n in named_resources(data).items() if n == image)
    tex = render.surf_image(data, parse_toc(data), index).astype(np.float64) / 255
    grey = tex[:, :, :3].mean(2, keepdims=True)
    tex[:, :, :3] = np.clip(grey + (tex[:, :, :3] - grey) * colour, 0, 1)
    tex[:, :, 3] = 1.0
    a, p = np.radians(yaw), np.radians(pitch)
    right = np.array((np.cos(a), np.sin(a), 0.0))
    look = np.array((-np.sin(a), np.cos(a), 0.0)) * np.cos(p) - np.array((0, 0, 1.0)) * np.sin(p)
    up = np.cross(right, look)
    parts = [q for q in parts if len(q.T)]
    allp = np.concatenate([q.P for q in parts])
    centre = (allp.max(0) + allp.min(0)) / 2
    for q in parts:
        n = q.P - centre
        n /= np.maximum(np.sqrt(dot(n, n)), 1e-12)[:, None]
        q.UV = np.stack([dot(n, right) * 0.5 + 0.5, -dot(n, up) * 0.5 + 0.5], 1)
        q.tex, q.tint = tex, np.ones_like(q.tint)
    return parts

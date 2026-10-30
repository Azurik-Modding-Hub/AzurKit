#!/usr/bin/env python3
"""Render the Randomize tab's and the maps' icons from the game's own 3D models (Step 2.52, D191).

Each icon is a model drawn with its own textures (``azurik_mod/xbr/draw.py``):
an item's character body (characters.xbr, the ``critters_engine`` body
config.xbr names), or a barrier's platform meshes as a level places them,
seen in a 3/4 view (a key upright, each key the vanilla data places its
own) under one light on a transparent ground, at ``SS`` times the size and
box-filtered down to 20 px.  An opaque part is cut out where its texture's
alpha is under its material's reference, as the game draws it (a key
card's plate).  The fire barrier is particles with no mesh, so its drawn
flame stays; the smash wall, a faint glow plane, is drawn here
(:data:`DRAWN`).  The fuel's sphere wears fx.xbr's chroma field, the colours
the game puts on the chromatic fuel, mapped by the surface's facing (D203).

Usage (needs the vanilla ISO)::

    uv run --locked python scripts/render_model_icons.py [--iso PATH] [--out DIR] [--size PX]

A few seconds; prints each icon's name.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from azurkit.tools.randomizer.art.draw import OUTLINE, PITCH, SS, Part, dot, down, draw

REPO = Path(__file__).resolve().parent.parent
# icon: (source, yaw in degrees); a source is ("body", <characters.xbr body>)
# or ("barrier", <level>, <its id in the level's generated file>).  Each key
# the vanilla data places is its own icon, named for it (``keys``).
ICONS = {
    "frag_air": (("body", "frag_air_1"), 20), "frag_earth": (("body", "frag_earth_1"), 20),
    "frag_fire": (("body", "frag_fire_1"), 20), "frag_water": (("body", "frag_water_1"), 20),
    "frag_life": (("body", "frag_life_1"), 20),
    "power_air": (("body", "power_air"), 30), "power_earth": (("body", "power_earth"), 30),
    "power_fire": (("body", "power_fire"), 30), "power_water": (("body", "power_water"), 30),
    "power_life": (("body", "power_life"), 30), "power_ammo": (("body", "power_ammo"), 30),
    "power_staff1": (("body", "power_staff1"), 30), "power_staff2": (("body", "power_staff2"), 30),
    "gem_diamond": (("body", "diamond"), 30), "gem_emerald": (("body", "emerald"), 30),
    "gem_ruby": (("body", "ruby"), 30), "gem_sapphire": (("body", "sapphire"), 30),
    "obsidian": (("body", "obsidian"), 0),
    "fuel": (("body", "large_chromatic_fuel"), 30), "health": (("body", "large_health"), 30),
    "crystal": (("barrier", "e5", "e5/g0/r2304"), 30),
    "ice_block": (("barrier", "w1", "w1/g0/r1433"), 35),
    "acid_block": (("barrier", "a1", "a1/g0/r2356"), 35),
}
# D193 (Step 2.53): the icons weak at 20 px, tuned, still drawn from their
# models: "colours" multiplies in a barrier's vertex colours (each mesh's
# mean, the model's own colour) as the game does (MODULATE2X: twice), "gain"
# brightens, "roll" turns the view in the picture's plane (a long model
# across the diagonal) and "rim" is the rim's colour.  D203 (Step 2.57,
# the owner's picks): the obsidian upright, seen from the front; the fuel
# wearing a ``skin`` (an XBR's image, its colour times a factor).  Step 2.84
# (D193's rest): the two staff powers, the darkest on the maps' disc,
# brightened, the thin second one also turned across the diagonal.
LOOKS = {
    "power_staff1": {"gain": 2.0},
    "power_staff2": {"gain": 3.0, "roll": 45.0},
    "frag_earth": {"gain": 1.7},
    "acid_block": {"colours": True, "gain": 3.0},
    "ice_block": {"colours": True},
    "crystal": {"colours": True, "gain": 12.0, "rim": (190, 196, 204)},
    "obsidian": {"pitch": 5.0, "gain": 1.5},
    "fuel": {"skin": ("gamedata/fx.xbr", "fx/jdtchromafield_000.tif", 2.0)},
}
KEY_VIEW = (15.0, 5.0)          # a key's yaw and pitch: upright, its gem showing (the owner's pick)


# --------------------------------------------------------------------------- models
def body_parts(rd, cache: dict, body: str) -> list[Part]:
    """A character body's parts (characters.xbr, read once into ``cache``)."""
    from azurkit.tools.randomizer.art import render
    from azurkit.tools.randomizer.ports import named_resources, parse_toc

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


def keys() -> list[str]:
    """The keys the vanilla data places (R1.1's generated files); each body
    is named for its key."""
    import json

    from azurkit.tools.randomizer.levels import GENERATED

    return sorted({loc["item"] for path in GENERATED.glob("*.json")
                   for loc in json.loads(path.read_text(encoding="utf-8"))["locations"]
                   if loc["item"].startswith("key_")})


def icon(rd, schema, cache: dict, name: str, size: int = 20) -> np.ndarray:
    """``ICONS[name]``, or a key's own model, drawn with its ``LOOKS``:
    (size, size, 4) RGBA uint8."""
    if name.startswith("key_"):
        yaw, pitch = KEY_VIEW
        return draw(body_parts(rd, cache, name), yaw, size, pitch)
    if name in DRAWN:
        return DRAWN[name](size)
    (src, yaw), look = ICONS[name], dict(LOOKS.get(name, {}))
    colours, skin = look.pop("colours", False), look.pop("skin", None)
    parts = body_parts(rd, cache, src[1]) if src[0] == "body" else barrier_parts(rd, schema, *src[1:], colours)
    if skin:
        parts = skinned(rd, parts, *skin, yaw, look.get("pitch", PITCH))
    return draw(parts, yaw, size, **look)


def skinned(rd, parts: list[Part], xbr: str, image: str, colour: float, yaw: float, pitch: float) -> list[Part]:
    """``parts`` (glow sprites left out) wearing ``xbr``'s ``image``, opaque,
    its colour's distance from grey times ``colour``, mapped by each point's
    facing from the model's centre as seen from ``yaw``/``pitch`` (a sphere
    map)."""
    from azurkit.tools.randomizer.art import render
    from azurkit.tools.randomizer.ports import named_resources, parse_toc

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

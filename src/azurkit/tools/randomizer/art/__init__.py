"""The item tracker's pictures, drawn from the player's own image at first
use (Step 4.2c3: no picture of the game is in the wheel, the app or the
site): each level's map, its floors seen from above in the colours the
level shows, with where its exits, items, spots,
barriers, features and gems lie on it (``maps.json``'s entry), the world
map of every level's main floor, and the item icons, each the game's own
model at 20 px. Modkit draws them by its scripts ``render_level_maps.py``
and ``render_model_icons.py`` (installed as :mod:`.maps` and :mod:`.icons`
by the oracle sync, with the readers they draw from: the level node graphs
on the node-type names table, the collision and render meshes, the model
drawer, and the reach model's first stage, :mod:`.reach`); the same image
draws the same pixels here (``tests/test_art.py`` holds them to Modkit's
pictures on both releases).

The work comes in :data:`~azurkit.tools.randomizer.tracking.ART_PARTS`'
parts, each one call (:func:`part`): the icons, then each level of the world
map (a few seconds each, w1's longest), whose main floor's thumbnail the
world map is made of (:func:`world`). Each reads only the files it draws
from, each checked against its release's vanilla file as it is read
(:class:`Vanilla`). A host keeps what they give (the app in its cache
folder, the site in the browser's storage) and draws a part once. A coarse
level's floors are drawn again finer for the Tracker's zoom (:func:`detail`,
Modkit's detail pictures, by :func:`detail_factor`), by the recorder alone:
they ship with the page. numpy does the drawing: this package and ``draft/`` are the randomizer's only
importers of it, and the site loads it only for them.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib

import numpy as np

if np.dtype(np.intp).itemsize < 8:   # the site's numpy (Pyodide's, wasm32) indexes with 32-bit ints, and Modkit's
    _repeat, _bincount = np.repeat, np.bincount   # drawing hands np.repeat and np.bincount int64 counts, which they
    #                                               refuse to cast down: their values fit, so they are cast first

    def _intp(x):
        return x.astype(np.intp) if isinstance(x, np.ndarray) and x.dtype == np.int64 else x

    np.repeat = lambda a, repeats, axis=None: _repeat(a, _intp(repeats), axis)
    np.bincount = lambda x, weights=None, minlength=0: _bincount(_intp(x), weights, minlength)

from azurkit.core import gate, inflate  # noqa: E402
from azurkit.tools.randomizer.art import icons, maps, nodes  # noqa: E402
from azurkit.tools.randomizer.ports import XisoReader  # noqa: E402

__all__ = ["Vanilla", "detail", "detail_factor", "digest", "index", "part", "png", "unpng", "world"]
SIGNATURE = (0x89504E470D0A1A0A).to_bytes(8, "big")   # a PNG's (the XBE holds one too: no 8-byte literal of it)
# The detail pictures (Modkit's Step 2.97, D278; shipped since Step 4.3l, D988): a level's map coarser than
# DETAIL_PX_M / DETAIL_MIN px a metre ships again at DETAIL_PX_M (the reach model's 0.5 m columns), which the
# Tracker's map shows once it is zoomed past its own pixels (Modkit's gui/rando_view.py's numbers).
DETAIL_PX_M, DETAIL_MIN = 2.0, 1.25


class Vanilla:
    """The image at ``source`` read file by file (Modkit's ``XisoReader``'s
    :meth:`read_file`), each file checked against the vanilla file of the
    release whose ``default.xbe`` it holds: ``gate.NotVanillaError`` names
    the first that isn't (a missing one, another's bytes)."""

    def __init__(self, source) -> None:
        self._reader = XisoReader(source)
        self.release: gate.Release | None = None

    def __enter__(self) -> Vanilla:
        self._reader.__enter__()
        try:
            xbe = self._reader.read_file("default.xbe")
        except (OSError, ValueError, KeyError):
            xbe = b""
        sha = hashlib.sha256(xbe).hexdigest()
        self.release = next((r for r in gate.RELEASES if r.files["default.xbe"][1] == sha), None)
        if self.release is None:
            self._reader.__exit__(None, None, None)
            raise gate.NotVanillaError("the maps are drawn from a vanilla image: its default.xbe is no release's")
        self.xbe = xbe
        return self

    def __exit__(self, *exc) -> None:
        self._reader.__exit__(*exc)

    def read_file(self, path: str) -> bytes:
        if path == "default.xbe":
            return self.xbe
        vanilla = self.release.files.get(path)
        try:
            data = self._reader.read_file(path)
        except (OSError, ValueError, KeyError):
            raise gate.NotVanillaError(f"{path}: missing from the image") from None
        if vanilla is None or hashlib.sha256(data).hexdigest() != vanilla[1]:
            raise gate.NotVanillaError(f"{path}: its contents differ from the vanilla {self.release.label} file")
        return data


def digest(img: np.ndarray) -> str:
    """A picture's digest: the sha256 of ``"<width>x<height>x<channels>\\n"``
    and its pixels, rows top to bottom (the oracle sync's ``pixel_digest``
    of Modkit's PNGs)."""
    h, w, c = img.shape
    return hashlib.sha256(f"{w}x{h}x{c}\n".encode() + np.ascontiguousarray(img, dtype=np.uint8).tobytes()).hexdigest()


def png(img: np.ndarray) -> bytes:
    """An RGB or RGBA picture (rows top to bottom) as the PNG Modkit writes
    of it (its ``svg._png`` and ``draw.png_rgba``: no filter, deflated at 9)."""
    h, w, c = img.shape
    img = np.ascontiguousarray(img, dtype=np.uint8)
    raw = b"".join(b"\x00" + img[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6 if c == 4 else 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def unpng(data: bytes) -> np.ndarray:
    """A picture :func:`png` wrote, read back (no filter: ``ValueError`` for another PNG), its rows
    inflated through ``core.inflate`` (D992's SEC-5: at most 4096x4096, one byte past its rows)."""
    if data[:8] != SIGNATURE:
        raise ValueError("not a PNG")
    at, idat, head = 8, [], None
    while at + 8 <= len(data):
        (n,), tag = struct.unpack_from(">I", data, at), data[at + 4:at + 8]
        body, at = data[at + 8:at + 8 + n], at + 12 + n
        head = struct.unpack(">IIBBBBB", body) if tag == b"IHDR" else head
        idat += [body] if tag == b"IDAT" else []
    if head is None or head[2] != 8 or head[3] not in (2, 6) or head[6]:
        raise ValueError("a PNG AzurKit didn't write")
    w, h, c = head[0], head[1], 3 if head[3] == 2 else 4
    rows = np.frombuffer(inflate.png_rows(b"".join(idat), w, h, c), dtype=np.uint8).reshape(h, w * c + 1)
    if rows[:, 0].any():
        raise ValueError("a PNG AzurKit didn't write (a filtered row)")
    return rows[:, 1:].reshape(h, w, c).copy()


def part(reader: Vanilla, name: str) -> dict:
    """One part of the pictures from ``reader``'s image: ``"icons"``
    (``{"pictures": {"icons/<icon>": RGBA}}``, every icon Modkit's script
    draws: the items' and barriers' models, each key's own, and the smash
    wall's drawing), or a level of the world map (``{"pictures": {floor:
    RGB}, "entry": its maps.json entry, "thumb": its main floor's world-map
    thumbnail}``)."""
    schema = nodes.Schema(reader.read_file("default.xbe"))
    if name == "icons":
        cache: dict = {}
        return {"pictures": {f"icons/{n}": icons.icon(reader, schema, cache, n)
                             for n in [*icons.ICONS, *icons.DRAWN, *icons.keys()]}}
    if name not in maps.GRID:
        raise ValueError(f"art: no part {name!r} (the icons, or a level of the world map)")
    pictures, entry = maps.render(reader, schema, name)
    return {"pictures": pictures, "entry": entry, "thumb": maps.thumb(pictures[name], maps.THUMB)}


def detail_factor(entry: dict) -> float | None:
    """How many times finer than its map a level's detail pictures are,
    from its ``maps.json`` entry (its frame's px a metre): None when its map
    is fine enough to have none (Modkit's ``detail_factor``)."""
    r = DETAIL_PX_M / entry["frame"][2]
    return r if r >= DETAIL_MIN else None


def detail(reader: Vanilla, level: str, factor: float) -> dict[str, np.ndarray]:
    """A level's detail pictures from ``reader``'s image (``{"detail/<floor>":
    RGB}``): each floor of its map drawn ``factor`` times finer
    (:func:`detail_factor`), on the same floors in the same colours, its
    pixel u the map's pixel u / ``factor`` (Modkit's ``draw_detail``)."""
    if level not in maps.GRID:
        raise ValueError(f"art: no level {level!r} of the world map")
    pictures, _ = maps.render(reader, nodes.Schema(reader.read_file("default.xbe")), level, factor)
    return {f"detail/{name}": img for name, img in pictures.items()}


def world(thumbs: dict[str, np.ndarray]) -> tuple[np.ndarray, dict]:
    """The world map (every level's main floor on its grid cell, Modkit's
    ``world.png``) from each level's ``thumb`` (:func:`part`), and its
    entry in ``maps.json`` (``{"title", "levels": {level: [x, y, w, h]}}``)."""
    width = maps.CELL[0] * (1 + max(c for c, _ in maps.GRID.values()))
    height = maps.WORLD_TOP + maps.CELL[1] * (1 + max(r for _, r in maps.GRID.values()))
    out = np.empty((height, width, 3), dtype=np.uint8)
    out[:] = maps.BACKGROUND.astype(np.uint8)
    placed = {}
    for level in (lv for lv in maps.LEVELS if lv in maps.GRID):
        t = thumbs[level]
        col, row = maps.GRID[level]
        ox = col * maps.CELL[0] + (maps.CELL[0] - t.shape[1]) // 2
        oy = maps.WORLD_TOP + row * maps.CELL[1] + (maps.CELL[1] - t.shape[0]) // 2
        out[oy:oy + t.shape[0], ox:ox + t.shape[1]] = t
        placed[level] = [ox, oy, t.shape[1], t.shape[0]]
    return out, {"title": "Perathia", "levels": placed}


def index(entries: dict[str, dict], world_entry: dict) -> str:
    """``maps.json`` as Modkit writes it, of each level's entry and the world's."""
    return json.dumps({"world": world_entry, "levels": entries}, indent=1, sort_keys=True) + "\n"

"""The item tracker's pictures (Step 4.2c3), shipped with the page since
Step 4.3f (D961): every level's maps, the world map, the maps' index and
the item icons in ``web/art/`` (``scripts/record_goldens.py``'s art
family; the maps Modkit's committed pictures pixel for pixel at the last
cut, Step 4.12b) are what the tracker's drawing gives from each release's image,
byte for byte, and nothing else is shipped."""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import json
import math
import multiprocessing
import struct
import zlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from azurkit import sdk
from azurkit.core import gate
from azurkit.tools.randomizer import art, tracking
from scripts import record_goldens
from tests import _hosts

ROOT = Path(__file__).resolve().parent.parent
WORKERS = 4      # the levels drawn at once (a few seconds each, w1's longest; D926: a bench's most above load 40)
ART = ROOT / "src" / "azurkit" / "tools" / "randomizer"
DRAWN = ("draft", "art", "levels.py", "data/generated")   # what draws them: the version names its sources
SHIPPED = f"{record_goldens.ART}/{tracking.ART_VERSION}/"
DETAIL = ("a6", "f2")   # the coarse levels whose detail pictures the test draws (4.7 + 7.2 s; the rest: --check)
APART, FEW = 200, 4   # close enough (D1016): at most one pixel or table byte in this many other, or this few pixels
BOX, CROWD = 40, 8    # and in no 40 px box (the icon sheet's tile) more than one pixel in 8: x86's rounding moved 84 of
#                       one box's 1,600 (airship.png, Step 4.4ci9), a box-sized change moves 400 or more in one


def _sha256(files: dict[str, bytes]) -> dict[str, str]:
    return {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}


def _inflated(text):
    """A JSON string's deflated bytes (``maps.storeys``'s), or None for any other string."""
    with contextlib.suppress(binascii.Error, ValueError, TypeError, zlib.error):
        return zlib.decompress(base64.b64decode(text, validate=True))
    return None


def _near(got, want, path: str = "") -> list[str]:
    """How one host's ``maps.json`` or ``floors.json`` value is not another's: ints, keys, lengths and strings exact,
    floats within 1e-9 (one part in a billion, their shortest repr's last digits), a deflated table's rows the same
    length with at most one byte in :data:`APART` differing."""
    if isinstance(want, dict) and isinstance(got, dict) and got.keys() == want.keys():
        return [why for key in want for why in _near(got[key], want[key], f"{path}/{key}")]
    if isinstance(want, list) and isinstance(got, list) and len(got) == len(want):
        return [why for i, (g, w) in enumerate(zip(got, want, strict=True)) for why in _near(g, w, f"{path}/{i}")]
    if isinstance(want, float) and isinstance(got, float) and math.isclose(got, want, rel_tol=1e-9, abs_tol=1e-9):
        return []
    if isinstance(want, str) and isinstance(got, str) and (rows := _inflated(want)) is not None and (
            made := _inflated(got)) is not None:
        if len(made) != len(rows):
            return [f"{path}: {len(made)} rows' bytes, not {len(rows)}"]
        off = sum(a != b for a, b in zip(made, rows, strict=True))
        return [f"{path}: {off} of {len(rows)} bytes differ"] if off > len(rows) // APART else []
    if got == want and type(got) is type(want):
        return []
    return [f"{path}: {type(got).__name__} vs {type(want).__name__}" + (f", {got} vs {want}" if isinstance(
        want, (int, float)) else "")]


def _boxes(shape: tuple, sheet: dict | None = None) -> dict[str, tuple[slice, slice]]:
    """A picture's boxes by name: the icon sheet's tiles (``sheet``: ``index.json``'s ``icons``), else :data:`BOX` px
    squares named by where they lie."""
    if sheet:
        t, n = sheet["tile"], sheet["columns"]
        return {name: (slice(i // n * t, (i // n + 1) * t), slice(i % n * t, (i % n + 1) * t))
                for i, name in enumerate(sheet["names"])}
    h, w = shape[:2]
    return {f"x {x}-{min(x + BOX, w) - 1}, y {y}-{min(y + BOX, h) - 1}": (slice(y, y + BOX), slice(x, x + BOX))
            for y in range(0, h, BOX) for x in range(0, w, BOX)}


def _pixels(got: np.ndarray, want: np.ndarray, boxes: dict | None = None, most: int = 0) -> list[str]:
    """Where two pictures of one size differ, never their bytes: how many pixels, by at most how much, within what
    box, then each of ``boxes`` (:func:`_boxes`) where more than ``most`` differ, by name."""
    off, by = (got != want).any(axis=-1), np.abs(got.astype(int) - want.astype(int)).max(axis=-1)
    ys, xs = np.nonzero(off)
    if not len(ys):
        return []
    return [f"{len(ys)} of {off.size} pixels differ, by at most {int(by.max())}, within x {xs.min()}-{xs.max()}, "
            f"y {ys.min()}-{ys.max()}"] + [f"{name}: {int(off[at].sum())} pixels, by at most {int(by[at].max())}"
                                           for name, at in (boxes or {}).items() if off[at].sum() > most]


def _apart(files: dict[str, bytes], kept: dict[str, bytes], exact: bool) -> dict[str, list[str]]:
    """``{rel: how it is not the kept file}``, nothing for a file that is. ``exact``: byte for byte (sha256s, and a
    picture's pixels and tiles where it differs, :func:`_pixels`). Else close enough (D1016; the kept files are the
    reference, so no host records its own): each JSON file by :func:`_near`, a picture's size exact and its pixels,
    not its bytes (Windows' zlib-ng deflates otherwise). The icon sheet's are all the same: its menu art sums
    integers and no pixel of its models moves with each sine, cosine and hypot 1e-8 off (Step 4.4ci9). A map's are
    at most :data:`APART`'s share other and one in :data:`CROWD` of any :data:`BOX` px box, as an edge's rounding
    moves a few (x86 under Rosetta: 250 of 226,080 at most, 84 in one box)."""
    index = files.get(f"{record_goldens.ART}/index.json")
    sheet = json.loads(index)["icons"] if index else None
    out = {}
    for rel, data in files.items():
        if data == kept[rel]:
            continue
        why = [f"sha256 {hashlib.sha256(data).hexdigest()[:12]}, not {hashlib.sha256(kept[rel]).hexdigest()[:12]}"]
        if rel.endswith(".png"):
            got, want = art.unpng(data), art.unpng(kept[rel])
            if got.shape != want.shape:
                why += [f"{got.shape} pixels, not {want.shape}"]
            elif exact or rel.endswith("/icons.png"):
                found = _pixels(got, want, _boxes(got.shape, sheet) if rel.endswith("/icons.png") else None)
                why = why + found if exact or found else []
            else:
                off, most = (got != want).any(axis=-1), BOX * BOX // CROWD
                crowded = any(off[at].sum() > most for at in _boxes(off.shape).values())
                why = why + _pixels(got, want, _boxes(off.shape), most) if crowded or off.sum() > max(
                    FEW, off.size // APART) else []
        elif not exact:
            why = _near(json.loads(data), json.loads(kept[rel]))
        if why:
            out[rel] = why[:16]
    return out


def test_the_shipped_maps_are_what_the_tracker_draws_from_each_image(usa_iso, europe_iso):
    """From the USA image every part (the icons, each level's floors, then
    the world map and maps.json from their entries and thumbnails), a6's
    and f2's detail pictures and the index (``ART_VERSION``, the icons'
    names and the detail factors) is the shipped file byte for byte (on
    another host's float maths, close enough: :func:`_apart`, D1016), and
    no other file is shipped but the other levels' detail pictures.
    Europe's image holds the same level, character and effect files (both
    manifests), so its maps differ only by
    what its own ``default.xbe`` gives the node graphs (its Euler tables, at
    its addresses): the icons and a level drawn from it are the same files.
    A part that isn't one is refused by name."""
    made = record_goldens.art(record_goldens.Images({gate.USA: usa_iso}), WORKERS, DETAIL)
    levels = json.loads(made[f"{SHIPPED}maps.json"])["levels"]
    finer = {f"{SHIPPED}detail/{floor}.png" for lv in DETAIL for floor in levels[lv]["floors"]}
    kept = record_goldens.kept_files((record_goldens.ART,))
    assert sorted(made) == sorted(rel for rel in kept if "/detail/" not in rel or rel in finer)
    assert _apart(made, kept, _hosts.recording()) == {}
    with ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("spawn")) as pool:
        europe = dict(pool.map(record_goldens._art_part, [(str(europe_iso), part) for part in ("icons", "e6")]))
    drawn = {f"{SHIPPED}{name}.png": png for part in europe.values() for name, png in part["pictures"].items()}
    assert _sha256(drawn) == _sha256({rel: made[rel] for rel in drawn})
    vanilla = gate.USA.files, gate.EUROPE.files
    read = [p for p in vanilla[0] if p.startswith("gamedata/") and p.endswith(".xbr") and "index" not in p]
    assert read and all(vanilla[0][p] == vanilla[1][p] for p in read)
    with pytest.raises(ValueError, match="no part 'w9'"):
        sdk.art(str(usa_iso), "w9")


def test_another_hosts_pictures_are_close_enough_only_by_a_few_edge_pixels_and_its_floats_last_digits():
    """D1016: off the recording host a map may have a few other pixels and a JSON float its last digits, nothing
    more: many pixels, a box's worth in one place, another size, an integer, a key or a float far off is named; on it,
    any byte is. The icon sheet's pixels are every host's (Step 4.4ci9): an icon recoloured, blanked or one pixel
    off is named by its tile, its pixels deflated otherwise (Windows' zlib-ng) only on the recording host."""
    img = np.zeros((400, 400, 3), np.uint8)
    edge, many, block = img.copy(), img.copy(), img.copy()
    edge[0, 0], many[:10], block[50:75, 50:75] = 90, 90, 90   # the block: 625 pixels, under the share's 800
    doc = {"frame": [1.5, 2.0], "count": 3, "name": "a", "rows": base64.b64encode(zlib.compress(bytes(1000))).decode()}
    def apart(file: str, data: bytes, want: bytes, exact: bool = False) -> list[str]:
        return _apart({file: data}, {file: want}, exact).get(file, [])

    assert apart("a.png", art.png(edge), art.png(img)) == []
    assert "4000 of 160000 pixels differ" in apart("a.png", art.png(many), art.png(img))[1]
    assert apart("a.png", art.png(block), art.png(img))[1:] == [
        "625 of 160000 pixels differ, by at most 90, within x 50-74, y 50-74",
        "x 40-79, y 40-79: 625 pixels, by at most 90"]
    assert "pixels, not" in apart("a.png", art.png(img[:50]), art.png(img))[1]
    assert apart("a.png", art.png(edge), art.png(img), exact=True)[0].startswith("sha256")
    index, shipped = (ROOT / record_goldens.ART / "index.json").read_bytes(), (ROOT / SHIPPED / "icons.png").read_bytes()
    picture, at = art.unpng(shipped), _boxes((), json.loads(index)["icons"])["obsidian"]
    recoloured, blank, dot = picture.copy(), picture.copy(), picture.copy()
    recoloured[at], blank[at], dot[at][20, 20, 0] = picture[at][..., [2, 1, 0, 3]], 0, picture[at][20, 20, 0] ^ 1
    def sheet(data: bytes, exact: bool = False) -> list[str]:
        name = f"{SHIPPED}icons.png"
        files = {f"{record_goldens.ART}/index.json": index, name: data}
        return _apart(files, files | {name: shipped}, exact).get(name, [])

    for icon in (recoloured, blank, dot):
        assert sheet(art.png(icon))[-1].startswith("obsidian: ")
    with pytest.MonkeyPatch.context() as patched:
        patched.setattr(zlib, "compress", lambda data, level=-1, deflate=zlib.compress: deflate(data, 1))
        again = art.png(picture)
    assert again != shipped and sheet(again) == [] and sheet(again, exact=True)[0].startswith("sha256")
    near = doc | {"frame": [1.5 * (1 + 1e-12), 2.0]}
    assert apart("m.json", json.dumps(near).encode(), json.dumps(doc).encode()) == []
    assert apart("m.json", json.dumps(near).encode(), json.dumps(doc).encode(), exact=True)[0].startswith("sha256")
    for other in ({"frame": [1.6, 2.0]}, {"count": 4}, {"name": "b"}, {"rows": base64.b64encode(zlib.compress(
            bytes(999))).decode()}, {"rows": base64.b64encode(zlib.compress(b"\1" * 1000)).decode()}, {"more": 1}):
        assert apart("m.json", json.dumps(doc | other).encode(), json.dumps(doc).encode())


def test_the_art_version_names_the_drawings_sources():
    """The pictures ship under ``ART_VERSION``: a change to what draws them
    (the drawing's modules, the reach model's first stage, the level
    semantics or the generated data, ported from Modkit) moves its
    digest, so the version changes with it and the recorder draws them
    again (the test above fails until it has)."""
    files = sorted(p for name in DRAWN for p in ((ART / name).rglob("*") if (ART / name).is_dir() else [ART / name])
                   if p.is_file() and "__pycache__" not in p.parts)
    lines = "".join(f"{p.relative_to(ART).as_posix()} {hashlib.sha256(p.read_bytes()).hexdigest()}\n" for p in files)
    assert tracking.ART_VERSION == f"1-{hashlib.sha256(lines.encode()).hexdigest()[:12]}"


def test_the_icon_sheet_has_a_tile_for_everything_the_lists_and_maps_show_and_each_fragment_its_own():
    """Every item the vanilla data places (the 4 large element fuels once had no icon anywhere) and every icon of the
    Randomizer's item rows has a tile with something on it, but the fire barrier, whose drawing is the page's; the 20
    fragments' tiles all differ; ``icons.css`` names each tile where ``index.json`` says it lies."""
    from azurkit.tools import randomizer

    root = ROOT / record_goldens.ART
    sheet = json.loads((root / "index.json").read_text())["icons"]
    tile, columns, names = sheet["tile"], sheet["columns"], sheet["names"]
    picture = art.unpng((ROOT / SHIPPED / "icons.png").read_bytes())
    tiles = {n: picture[i // columns * tile:(i // columns + 1) * tile, i % columns * tile:(i % columns + 1) * tile]
             for i, n in enumerate(names)}
    placed = {loc["item"] for path in (ART / "data" / "generated").glob("*.json")
              for loc in json.loads(path.read_text(encoding="utf-8"))["locations"]}
    assert {f"large_{e}_fuel" for e in ("air", "earth", "fire", "water")} <= placed
    shown = {tracking.icon(item) for item in placed} | {i for row in randomizer.ITEMS for i in row[4]}
    assert sorted(shown - set(names)) == ["fire_barrier"]
    assert [n for n in names if (tiles[n][:, :, 3] > 128).sum() < tile] == []
    fragments = [tiles[n].tobytes() for n in names if n.startswith("frag_")]
    assert len(fragments) == len(set(fragments)) == 20
    css = (root / "icons.css").read_text()
    assert f"url({tracking.ART_VERSION}/icons.png)" in css
    for i, n in enumerate(names):
        assert (f".glyph.{n} {{ background-position: calc(var(--g) * {-(i % columns)}) "
                f"calc(var(--g) * {-(i // columns)}); }}") in css


def test_a_menu_icon_shrinks_to_each_pixels_exact_mean_rounded_half_up_whatever_the_machine():
    """The sheet's menu art shrank by float sums in BLAS's order, which differs by chip and macOS, so a mean on a
    tie rounded either way and GitHub's M1 drew another ``icons.png`` (Step 4.4ci8). Three pixels in a row go to
    two: the first new one is two thirds of the first (alpha 255) and a third of the second (alpha 170), so its
    green is (2 * 71 * 255 + 97 * 170) / 680 = 77.5 exactly, 78, and its alpha 680 / 3, 227."""
    row = np.array([[[131, 71, 23, 255], [247, 97, 147, 170], [205, 25, 72, 204]]], np.uint8)
    assert art.icons.fit(row, 2).tolist() == [[[160, 78, 54, 227], [217, 46, 94, 193]], [[0, 0, 0, 0]] * 2]


def test_each_coarse_levels_floors_ship_drawn_at_two_pixels_a_metre():
    """A level whose map has fewer than 2 / 1.25 px a metre ships each of
    its floors again at 2 px a metre (Modkit's detail pictures,
    ``art.detail_factor``): ``index.json``'s ``detail`` is that rule on
    ``maps.json``'s frames, 18 levels (f2 at 1.253 in, life at 1.015 out),
    and ``detail/`` holds each floor those levels name, its size its map's
    times the factor, and nothing else."""
    root = ROOT / SHIPPED
    detail = json.loads((ROOT / record_goldens.ART / "index.json").read_text())["detail"]
    levels = json.loads((root / "maps.json").read_text())["levels"]
    assert detail == {lv: f for lv, e in levels.items() if (f := art.detail_factor(e)) is not None}
    assert len(detail) == 18 and "f2" in detail and "life" not in detail and "life" in levels
    floors = {f"{floor}.png": lv for lv in detail for floor in levels[lv]["floors"]}
    assert sorted(p.name for p in (root / "detail").iterdir()) == sorted(floors)
    for name, lv in floors.items():
        size, f = struct.unpack(">II", (root / "detail" / name).read_bytes()[16:24]), detail[lv]
        assert all((n - 1) * f - 1 <= got <= n * f + 1 for n, got in zip(levels[lv]["size"], size)), name


def test_a_spot_shows_on_the_floor_of_the_room_it_stands_in():
    """A spot's floor is the one holding the most ground at its height round
    it (``maps.Rooms``, the rule ``floors.json`` gives Live's Follow too): the
    town temple's ten obsidian-lock rewards, each on a pedestal top no one
    walks on, show on town-5 with the temple's floor, not on the main floor
    their pedestals' own columns gave six of them; ``floors.json`` holds a
    table for every level of ``maps.json``."""
    root = ROOT / SHIPPED
    levels = json.loads((root / "maps.json").read_text())["levels"]
    town = levels["town"]
    at = {i["id"]: i["at"] for i in town["items"] + town["spots"]}
    assert {town["floors"][at[f"town/g1/r{r}"][2]] for r in range(15, 241, 25)} == {"town-5"}
    assert sorted(json.loads((root / "floors.json").read_text())["levels"]) == sorted(levels)


# --- Step 4.28c: Modkit's collision-mesh tests no AzurKit test pinned (the test census's lane C): the ``tern``
# reader's layout faults, each mesh's one owner and a platform's placed faces, on synthetic files.

def _tern(face=(0, 1, 2, 0), flags=0x8050, bmax=(1, 1, 0)) -> bytes:
    """A synthetic one-chunk ``tern``: a triangle with vertices at (0, 0, 0), (1, 0, 0) and (0, 1, 0) m, its
    chunk at 12, the u32 before the spatial structure at 56 and the structure at 60."""
    chunk = struct.pack("<3hBB3h3hH", 0, 0, 0, 3, 1, *bmax, 0, 0, 0, flags)
    chunk += struct.pack("<9h", 0, 0, 0, 256, 0, 0, 0, 256, 0) + bytes(face)
    return struct.pack("<IiI", 1, 56, 12) + chunk + bytes(8)


def _xbr(*entries) -> bytes:
    """A synthetic XBR: a 0x3C-byte header, the TOC of ``entries`` ((fourcc, payload) each) and their payloads."""
    toc, body = b"", b""
    for tag, payload in entries:
        toc += struct.pack("<II4sI", len(body), len(payload), tag.encode(), 0)
        body += payload
    head = b"xobx" + bytes(8) + struct.pack("<II", len(entries), 0x3C + 16 * len(entries))
    return head + bytes(0x3C - len(head)) + toc + body


def test_a_collision_mesh_that_breaks_the_layout_is_named_by_its_violation():
    """The ``tern`` reader (``art.tern``, Modkit's Step R1.2 port of the R0 evidence's reader, whose census of
    the disc found none) names each layout fault of a mesh: a face index past its chunk's vertices, a group byte
    out of order, flags the game doesn't set, a box that isn't its vertices' floor and ceiling, a chunk or tree
    past the payload and a payload too short for its header."""
    from azurkit.tools.randomizer.art import tern

    clean = tern.parse(_tern())
    assert (clean.violations, clean.n_vertices, clean.n_triangles) == ([], 3, 1)
    assert clean.chunks[0].verts == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    for buf, want in ((_tern(face=(0, 1, 3, 0)), ["face_index_out_of_range"]),
                      (_tern(face=(0, 1, 2, 1)), ["group_byte_order"]),
                      (_tern(flags=0x1234), ["unknown_flags"]),
                      (_tern(bmax=(2, 1, 0)), ["bbox_not_floor_ceil"]),
                      (_tern()[:40], ["chunk_past_next", "tree_out_of_range"]),
                      (_tern()[:8], ["short"])):
        assert tern.parse(buf).violations == want


def test_each_tern_has_one_owner_and_a_second_or_non_tern_reference_fails_the_load():
    """The ``levl`` payload's +0x00 names the level's static collision (``art.collision.owners``, Modkit's
    Q300); a reference to an entry that is not a ``tern``, or a second reference to one ``tern``, fails the load
    by name (every ``tern`` on the disc has exactly one owner)."""
    from types import SimpleNamespace

    from azurkit.tools.randomizer.art import collision

    schema = SimpleNamespace(types={"platform": SimpleNamespace(attrs=[])})
    ref = struct.pack("<I", 1)
    got = collision.owners(_xbr(("levl", ref), ("tern", _tern())), schema, graphs=[])
    assert [(o.kind, o.tern, [w for w, *_ in o.triangles()]) for o in got] == [("levl", 1, [0x8050])]
    for entries, why in (((("levl", struct.pack("<I", 0)), ("tern", _tern())), "TOC entry 0, which is not a tern"),
                         ((("levl", ref), ("tern", _tern()), ("levl", ref)), "tern 1, which already has an owner")):
        with pytest.raises(ValueError, match=why):
            collision.owners(_xbr(*entries), schema, graphs=[])


def test_a_platforms_collision_is_placed_by_its_world_matrix_with_the_word_its_attributes_give():
    """A platform's faces move with its world matrix and carry the word the platform builder 0x6AD20 makes
    (``art.collision.platform_word``): 0xC000, gameSolid 0x10 and 0x40 unless slippery and climbable are both
    set, water 0x100, and 0x20 on a non-solid word with water, a push or damage."""
    from azurkit.tools.randomizer.art import collision, nodes, tern

    w = collision.platform_word
    assert [w({}), w({"gameSolid": 1.0}), w({"gameSolid": 1.0, "slippery": 1.0, "climbable": 1.0}),
            w({"water": 1.0}), w({"pushEnable": 1.0}), w({"damage": 25.0}), w({"gameSolid": 1.0, "damage": 25.0})] == \
        [0xC000, 0xC050, 0xC013, 0xC120, 0xC028, 0xC020, 0xC050]
    mesh = tern.parse(_tern(flags=tern.PLATFORM_CHUNK))
    owner = collision.Owner("platform", 1, mesh, word=0xC050, world=nodes.translate(10.0, -2.0, 3.0))
    assert list(owner.triangles()) == [(0xC050, (10.0, -2.0, 3.0), (11.0, -2.0, 3.0), (10.0, -1.0, 3.0))]

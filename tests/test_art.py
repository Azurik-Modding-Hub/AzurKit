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


def _apart(files: dict[str, bytes], kept: dict[str, bytes], exact: bool) -> dict[str, list[str]]:
    """``{rel: how it is not the kept file}``, nothing for a file that is. ``exact``: byte for byte (sha256s). Else
    close enough (D1016; the kept files are the reference, so no host records its own): a picture's size exact and
    at most :data:`APART`'s share of its pixels other, as an edge's rounding moves a few (x86 under Rosetta: 250 of
    226,080 at most; Windows' zlib-ng deflates otherwise too, so its pixels are read, not its bytes), each JSON
    file by :func:`_near`."""
    out = {}
    for rel, data in files.items():
        if data == kept[rel]:
            continue
        if exact:
            why = [f"sha256 {hashlib.sha256(data).hexdigest()[:12]}, not {hashlib.sha256(kept[rel]).hexdigest()[:12]}"]
        elif rel.endswith(".png"):
            got, want = art.unpng(data), art.unpng(kept[rel])
            if got.shape != want.shape:
                why = [f"{got.shape} pixels, not {want.shape}"]
            else:
                off = (got != want).any(axis=-1)
                worst = int(np.abs(got.astype(int) - want.astype(int)).max())
                why = [f"{int(off.sum())} of {off.size} pixels differ, by at most {worst}"] if off.sum() > max(
                    FEW, off.size // APART) else []
        else:
            why = _near(json.loads(data), json.loads(kept[rel]))
        if why:
            out[rel] = why[:8]
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
    """D1016: off the recording host a picture may have a few other pixels and a JSON float its last digits, nothing
    more: many pixels, another size, an integer, a key or a float far off is named; on it, any byte is."""
    img = np.zeros((100, 100, 3), np.uint8)
    edge, many, table = img.copy(), img.copy(), base64.b64encode(zlib.compress(bytes(1000))).decode()
    edge[0, 0], many[:10] = 90, 90
    doc = {"frame": [1.5, 2.0], "count": 3, "name": "a", "rows": table}
    def apart(file: str, data: bytes, want: bytes, exact: bool = False) -> list[str]:
        return _apart({file: data}, {file: want}, exact).get(file, [])

    assert apart("a.png", art.png(edge), art.png(img)) == []
    assert "1000 of 10000 pixels differ" in apart("a.png", art.png(many), art.png(img))[0]
    assert "pixels, not" in apart("a.png", art.png(img[:50]), art.png(img))[0]
    assert apart("a.png", art.png(edge), art.png(img), exact=True)[0].startswith("sha256")
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

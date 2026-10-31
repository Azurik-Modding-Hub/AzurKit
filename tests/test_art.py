"""The item tracker's pictures (Step 4.2c3), shipped with the page since
Step 4.3f (D961): every level's maps, the world map, the maps' index and
the item icons in ``web/art/`` (``scripts/record_goldens.py``'s art
family; Modkit's committed pictures pixel for pixel at the last cut, Step
4.12b) are what the tracker's drawing gives from each release's image,
byte for byte, and nothing else is shipped."""

from __future__ import annotations

import hashlib
import json
import multiprocessing
import struct
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate
from azurkit.tools.randomizer import art, tracking
from scripts import record_goldens

ROOT = Path(__file__).resolve().parent.parent
WORKERS = 4      # the levels drawn at once (a few seconds each, w1's longest; D926: a bench's most above load 40)
ART = ROOT / "src" / "azurkit" / "tools" / "randomizer"
DRAWN = ("draft", "art", "levels.py", "data/generated")   # what draws them: the version names its sources
SHIPPED = f"{record_goldens.ART}/{tracking.ART_VERSION}/"
DETAIL = ("a6", "f2")   # the coarse levels whose detail pictures the test draws (4.7 + 7.2 s; the rest: --check)


def _sha256(files: dict[str, bytes]) -> dict[str, str]:
    return {rel: hashlib.sha256(data).hexdigest() for rel, data in files.items()}


def test_the_shipped_maps_are_what_the_tracker_draws_from_each_image(usa_iso, europe_iso):
    """From the USA image every part (the icons, each level's floors, then
    the world map and maps.json from their entries and thumbnails), a6's
    and f2's detail pictures and the index (``ART_VERSION``, the icons'
    names and the detail factors) is the shipped file byte for byte, and
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
    assert _sha256(made) == _sha256({rel: data for rel, data in kept.items() if "/detail/" not in rel or rel in finer})
    with ProcessPoolExecutor(2, mp_context=multiprocessing.get_context("spawn")) as pool:
        europe = dict(pool.map(record_goldens._art_part, [(str(europe_iso), part) for part in ("icons", "e6")]))
    drawn = {f"{SHIPPED}{name}.png": png for part in europe.values() for name, png in part["pictures"].items()}
    assert _sha256(drawn) == _sha256({rel: made[rel] for rel in drawn})
    vanilla = gate.USA.files, gate.EUROPE.files
    read = [p for p in vanilla[0] if p.startswith("gamedata/") and p.endswith(".xbr") and "index" not in p]
    assert read and all(vanilla[0][p] == vanilla[1][p] for p in read)
    with pytest.raises(ValueError, match="no part 'w9'"):
        sdk.art(str(usa_iso), "w9")


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

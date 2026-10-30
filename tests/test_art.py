"""The item tracker's pictures, drawn from the player's image (Step 4.2c3,
D3: none is in the repository): every level's maps, the world map, the maps'
index and the item icons are Modkit's pixel for pixel, read from each
release's image here and held to the digests of Modkit's committed pictures
(ORACLE.toml's ``rando.art``, the oracle sync's, never a picture)."""

from __future__ import annotations

import hashlib
import multiprocessing
import tomllib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pytest

from azurkit import sdk
from azurkit.core import gate
from azurkit.tools.randomizer import art, tracking

ROOT = Path(__file__).resolve().parent.parent
ORACLE = tomllib.loads((ROOT / "tests" / "oracle" / "ORACLE.toml").read_text(encoding="utf-8"))["rando"]["art"]
WORKERS = 4      # the levels drawn at once (a few seconds each, w1's longest; D926: a bench's most above load 40)
ART = ROOT / "src" / "azurkit" / "tools" / "randomizer"
DRAWN = ("draft", "art", "levels.py", "data/generated")   # what draws them: the version names its sources


def _drawn(iso: str, part: str) -> tuple[str, dict, dict]:
    """``part``'s pictures' digests from ``sdk.art`` (each PNG read back), its maps.json entry and its thumb."""
    got = sdk.art(iso, part)
    return part, {name: art.digest(art.unpng(png)) for name, png in got["pictures"].items()}, {
        key: got[key] for key in ("entry", "thumb") if key in got}


def _modkit(name: str) -> str:
    """The oracle's key for a picture ``sdk.art`` names: Modkit's path."""
    return f"gui/assets/{name}.png" if name.startswith("icons/") else f"gui/assets/maps/{name}.png"


def test_the_maps_and_icons_drawn_from_each_image_are_modkits_pixel_for_pixel(usa_iso, europe_iso):
    """From the USA image every part (the icons, each level's floors, then
    the world map and maps.json from their entries and thumbnails) is
    Modkit's: each picture's pixels and the index's text. Europe's image
    holds the same level, character and effect files (both manifests), so
    its maps differ only by what its own ``default.xbe`` gives the node
    graphs (its Euler tables, at its addresses): the icons and a level drawn
    from it are Modkit's too. A file that isn't its release's is refused by
    name, and the oracle holds every picture drawn but the fire barrier's
    flame (drawn for the page, no model of the game)."""
    with ProcessPoolExecutor(WORKERS, mp_context=multiprocessing.get_context("spawn")) as pool:
        drawn = {part: (pics, extra) for part, pics, extra in
                 pool.map(_drawn, [str(usa_iso)] * len(tracking.ART_PARTS), tracking.ART_PARTS)}
        europe = {part: pics for part, pics, _ in pool.map(_drawn, [str(europe_iso)] * 2, ("icons", "e6"))}
    world = sdk.art_world({lv: drawn[lv][1] for lv in tracking.GRID})
    pictures = {_modkit(name): d for pics, _ in drawn.values() for name, d in pics.items()}
    pictures[_modkit("world")] = art.digest(art.unpng(world["pictures"]["world"]))
    pictures["gui/assets/maps/maps.json"] = hashlib.sha256(world["text"].encode()).hexdigest()
    assert pictures == {rel: d for rel, d in ORACLE.items() if rel != "gui/assets/icons/fire_barrier.png"}
    assert {_modkit(n): d for part in ("icons", "e6") for n, d in europe[part].items()} == {
        _modkit(n): d for part in ("icons", "e6") for n, d in drawn[part][0].items()}
    vanilla = gate.USA.files, gate.EUROPE.files
    read = [p for p in vanilla[0] if p.startswith("gamedata/") and p.endswith(".xbr") and "index" not in p]
    assert read and all(vanilla[0][p] == vanilla[1][p] for p in read)
    with pytest.raises(ValueError, match="no part 'w9'"):
        sdk.art(str(usa_iso), "w9")


def test_the_art_version_names_the_drawings_sources():
    """A host keeps the pictures under ``ART_VERSION``: a change to what
    draws them (the drawing's modules, the reach model's first stage, the
    level semantics or the generated data, each Modkit's by the sync) moves
    its digest, so the version changes with it and a host draws them again."""
    files = sorted(p for name in DRAWN for p in ((ART / name).rglob("*") if (ART / name).is_dir() else [ART / name])
                   if p.is_file() and "__pycache__" not in p.parts)
    lines = "".join(f"{p.relative_to(ART).as_posix()} {hashlib.sha256(p.read_bytes()).hexdigest()}\n" for p in files)
    assert tracking.ART_VERSION == f"1-{hashlib.sha256(lines.encode()).hexdigest()[:12]}"

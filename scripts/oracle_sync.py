"""Copy Modkit's oracle bundle for the given families into ``tests/oracle/``.

    uv run --locked python scripts/oracle_sync.py --modkit PATH --ref REF --tag NAME --family core --family packs

The script clones Modkit at REF into a scratch folder. It uses ``git clone
--shared``, so Modkit's checkout and refs are left as they are. It then runs
Modkit's own ``scripts/export_oracle.py`` there, in Modkit's locked
environment, and replaces each family's folder in ``tests/oracle/`` with the
bundle's. ``tests/oracle/ORACLE.toml`` records each family's tag (the Modkit
tag the bundle is cut at), its commit and the sha256 of every file;
``tests/test_oracle.py`` checks every file against it.

When a family was synced before, the script prints Modkit's commits since that
sync that touch the family's paths. That list is the port's to-do. AzurKit never
imports Modkit: the bundle holds sha256s, names and recipes (never game bytes).
The facts' build spans (``patch_sites.<va>.new.<case>``, a build's bytes over
a site, vanilla code included where the pack leaves it) are installed as their
sha256 and size (:func:`digest_spans`); ORACLE.toml's ``exported`` table keeps
each such file's sha256 as exported, which Modkit's ``oracle.json`` lists.

A family's sync also installs the Modkit source it ports as it is
(:data:`SOURCES`): the randomizer's data (and the movement tiers' margins),
copied verbatim, and its planner, writer, physics, movement, layer and
tracker, and Live's game reads, events and link to xemu (with the guest's
page tables and RAM layout they read through, Modkit's ``sim/pages.py`` and
``sim/recipes.py``), each module through :func:`port` (:data:`REWRITES`'
imports, and the statements :data:`DROPS` names taken out: what AzurKit's
engine can't hold, a process pool, Modkit's build objects, a file beside
the ISO). ORACLE.toml's ``source`` table keeps each installed file's
sha256, so a later Modkit fix arrives by the same sync, never by hand. A
module that still imports Modkit after its rewrites, or a statement DROPS
names that is gone, stops the sync before anything is written. The models
family's installs the archive writers a character swap builds on (Step
4.3a1): ``xbr/append.py`` (new resources and their relocations, grown
payloads), ``index.xbr``'s records, ``characters.xbr``'s bodies and clips
and the body codec.

Two of a family's files are the sync's own (:data:`DERIVED`), not Modkit's
bundle: the models family's ``swap.json``, the player-model swap's XBE hooks
(the ``swap`` section of Modkit's facts, both releases: each vanilla span it
writes as size and sha256, each address its shims call), and
``resources.json``, one sha256 per XBR resource of every G3 build that wears
a model, which ``scripts/modkit_resources.py`` makes by running Modkit's own
builds in the clone (checked against G3's per-file hashes first).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import tomllib
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORACLE = ROOT / "tests" / "oracle"
FAMILIES = ("core", "packs", "rando", "models")
FACTS = ("tests/facts/xbe.json", "tests/facts/xbe.europe.json")   # their build spans are installed as digests
PATHS = {   # where each family's code and records live in Modkit (its tag bump's commit list)
    "core": ("azurik_mod/iso", "azurik_mod/assets/vanilla.py", "azurik_mod/assets/filelist.py",
             "azurik_mod/assets/vanilla_manifest.json", "azurik_mod/assets/europe_manifest.json",
             "azurik_mod/assets/region_europe.json"),
    "packs": ("azurik_mod/patches", "azurik_mod/patching", "azurik_mod/xbe_tools", "azurik_mod/xbr",
              "azurik_mod/config", "shims", "tests/facts", "tests/goldens/packs.json",
              "tests/goldens/europe/packs.json", "tests/goldens/shims.json", "tests/goldens/xbr_editor.json",
              "tests/goldens/pipelines.json", "tests/goldens/europe/pipelines.json", "tests/goldens/gui.json"),
    "rando": ("azurik_mod/randomizer", "azurik_mod/sim/pages.py", "azurik_mod/sim/recipes.py",
              "tests/goldens/rando_plans.json", "tests/goldens/rando_iso.json",
              "tests/goldens/pipelines.json", "tests/goldens/europe/pipelines.json", "tests/goldens/gui.json",
              # the maps' and icons' drawing (Step 4.2c3) and the pictures Modkit commits of them (ART)
              *(f"azurik_mod/xbr/{name}" for name in ("nodes.py", "node_types.json", "tern.py", "collision.py",
                                                      "render.py", "draw.py")),
              "scripts/render_level_maps.py", "scripts/render_model_icons.py", "gui/assets/maps", "gui/assets/icons"),
    "models": ("azurik_mod/patches/player_model", "azurik_mod/patches/_player_*", "azurik_mod/assets",
               "azurik_mod/xbr/append.py", "tests/facts", "tests/goldens/shims.json", "tests/goldens/pipelines.json",
               "tests/goldens/europe/pipelines.json", "tests/goldens/gui.json"),
}
DERIVED = {"models": ("resources.json", "swap.json")}   # a family's files the sync makes itself (module docstring)
SWAP = (("usa", "tests/facts/xbe.json"), ("europe", "tests/facts/xbe.europe.json"))   # Modkit's facts: swap.json's


RANDO = "src/azurkit/tools/randomizer"
CHARACTERS = "src/azurkit/tools/characters"
LIVE = f"{RANDO}/live"   # the app's Live tracker (its link reads a running xemu): the contracts' app-only folder
ART = f"{RANDO}/art"     # the maps and icons drawn from the player's image (with draft/, the randomizer's numpy)
SOURCES = {   # Modkit's source a family's sync installs in AzurKit's: (Modkit's folder or file, AzurKit's, through port())
    "rando": (("azurik_mod/randomizer/data", f"{RANDO}/data", False),
              ("azurik_mod/randomizer/planner", f"{RANDO}/planner", True),
              *((f"azurik_mod/randomizer/{name}.py", f"{RANDO}/{name}.py", True)
                for name in ("writer", "physics", "movement", "layer", "tracker")),
              ("azurik_mod/randomizer/draft/tiers.toml", f"{RANDO}/draft/tiers.toml", False),   # physics reads it
              # Live (Step 4.2c2): the game's reads and the events (live.py), the link to xemu and the guest's
              # page tables and RAM layout it reads through
              ("azurik_mod/randomizer/live.py", f"{LIVE}/game.py", True),
              ("azurik_mod/randomizer/live_link.py", f"{LIVE}/link.py", True),
              *((f"azurik_mod/sim/{name}.py", f"{LIVE}/{name}.py", True) for name in ("pages", "recipes")),
              # The level maps and item icons drawn from the player's image (Step 4.2c3, D3): the reach model's
              # first stage (its geometry, floors and wiring, the level semantics they read), the level node
              # graphs with the node-type names table (P3: no capstone), the collision and render-mesh readers,
              # the model drawer, and Modkit's two scripts that draw them
              *((f"azurik_mod/randomizer/draft/{name}.py", f"{RANDO}/draft/{name}.py", True)
                for name in ("__init__", "envelope", "geometry", "floors", "wiring")),
              ("azurik_mod/randomizer/levels.py", f"{RANDO}/levels.py", True),
              *((f"azurik_mod/xbr/{name}", f"{ART}/{name}", True)
                for name in ("nodes.py", "node_types.json", "tern.py", "collision.py", "render.py", "draw.py")),
              ("scripts/render_level_maps.py", f"{ART}/maps.py", True),
              ("scripts/render_model_icons.py", f"{ART}/icons.py", True)),
    # the archive writers a swap builds on (Step 4.3a1): append and relocations in core, the rest the tool's
    "models": (("azurik_mod/xbr/append.py", "src/azurkit/core/xbr/append.py", True),
               *((f"azurik_mod/assets/{name}.py", f"{CHARACTERS}/{name}.py", True)
                 for name in ("characters", "body_codec", "index_xbr"))),
}
#: The pictures Modkit commits of what it draws from the image (Step 4.2c3): the level maps (``maps.json`` and each
#: floor's and the world's PNG) and the item icons, recorded in ORACLE.toml's ``<family>.art`` table as each
#: picture's :func:`pixel_digest` and ``maps.json``'s sha256 (D3: no picture is copied), which AzurKit's drawings
#: are held to (``tests/test_art.py``).
ART_FILES = {"rando": ("gui/assets/maps", "gui/assets/icons")}
OWN = frozenset({"azurik_mod/randomizer/planner/dbcache.py"})   # AzurKit's own instead: tools/randomizer/dbcache.py
REWRITES = (("from azurik_mod.randomizer.planner import dbcache", "from azurkit.tools.randomizer import dbcache"),
            # the tracker reads Live's events only: the site imports it, never the link
            ("from azurik_mod.randomizer.live import EPS,", "from azurkit.tools.randomizer.live.game import EPS,"),
            ("from azurik_mod.randomizer import live_link, writer", "from azurkit.tools.randomizer import writer"),
            ("from azurik_mod.randomizer.live_link import LiveError",
             "from azurkit.tools.randomizer.live.errors import LiveError"),
            ("from azurik_mod.sim import pages",
             "from azurkit.tools.randomizer.live import pages\nfrom azurkit.tools.randomizer.live.errors import LiveError"),
            ("from azurik_mod.sim import recipes", "from azurkit.tools.randomizer.live import recipes"),
            ("from azurik_mod.assets.vanilla import REGIONS, Region, UnmappedAddressError",
             "from azurkit.tools.randomizer.live.regions import REGIONS, Region, UnmappedAddressError"),
            # the maps' reach model: its first stage alone, AzurKit's (tools/randomizer/art/reach.py)
            ("from azurik_mod.randomizer.draft.reach import Reach", "from azurkit.tools.randomizer.art.reach import Reach"),
            ("from azurik_mod.randomizer import ", "from azurkit.tools.randomizer import "),
            ("azurik_mod.randomizer.", "azurkit.tools.randomizer."),
            ("from azurik_mod.xbr.nodes import", "from azurkit.core.xbr.nodes import"),
            # Modkit's xbr/edits.py's error and xbr/sections.py's index records (a file NOTICE.md credits to
            # JTCPP, D95): ours, in core/xbr/nodes.py
            ("from azurik_mod.xbr.edits import XbrStructuralError",
             "from azurkit.core.xbr.nodes import XbrStructuralError"),
            ("from azurik_mod.xbr.sections import IndexRecordsSection",
             "from azurkit.core.xbr.nodes import IndexRecordsSection"),
            ("from azurik_mod.xbr.append import", "from azurkit.core.xbr.append import"),
            ("from azurik_mod.xbr.toc_scan import named_resources, parse_toc",
             "from azurkit.tools.randomizer.ports import named_resources, parse_toc"),
            ("from azurik_mod.xbr.toc_scan import", "from azurkit.core.xbr.nodes import"),
            # the maps' and icons' XBR readers: Modkit's, in art/ (core/xbr is AzurKit's own)
            # the icons' script writes no PNG here (its main is dropped): art.png does, the site's and the app's
            ("from azurik_mod.xbr.draw import OUTLINE, PITCH, SS, Part, dot, down, draw, png_rgba",
             "from azurkit.tools.randomizer.art.draw import OUTLINE, PITCH, SS, Part, dot, down, draw"),
            ("from azurik_mod.xbr import ", "from azurkit.tools.randomizer.art import "),
            ("from azurik_mod.xbr.", "from azurkit.tools.randomizer.art."),
            ("from azurik_mod.assets.vanilla import xbe_layout", "from azurkit.tools.randomizer.ports import xbe_layout"),
            ("from azurik_mod.patching.xbe import resolve_va_to_file",
             "from azurkit.tools.randomizer.ports import resolve_va_to_file"),
            ("from azurik_mod.assets.filelist import listed", "from azurkit.tools.randomizer.ports import listed"),
            ("from azurik_mod.iso.xiso import XisoReader", "from azurkit.tools.randomizer.ports import XisoReader"))
DROPS = {   # top-level statements a ported module loses, by the names they bind
    "azurik_mod/randomizer/planner/fill.py": ("threading", "_ROLL_LOGIC", "_roll_chunk", "roll_seed"),   # the pool
    # its own source's sha256, read at import (Modkit's draft flights' cache key): the frozen app holds no .py
    "azurik_mod/randomizer/physics.py": ("hashlib", "SOURCE_SHA256"),
    # the slider tracks' safe ranges (the packs' registry, a platformdirs cache): the Randomize tab's (Step 4.2c)
    "azurik_mod/randomizer/movement.py": ("slider_ranges", "default_ranges"),
    # Modkit's build objects (IsoStaging, LayerLog, the swap's modules, the files beside the ISO): AzurKit's
    # generator layer (tools/randomizer/generator.py) writes, reads back and checks the movement in their place
    "azurik_mod/randomizer/layer.py": ("check_args", "write_layer", "check_movement", "movement_reasons", "judge",
                                       "outputs", "write_outputs"),
    # a build's placement file beside its ISO: the page hands the tracker the plan itself
    "azurik_mod/randomizer/tracker.py": ("json", "Path", "placements", "plan_doc"),
    # Live's session opens its link in the app (azurkit.app's feed), so the events need no socket on the site
    "azurik_mod/randomizer/live.py": ("connect",),
    # one LiveError, live/errors.py's, which the events raise too (the rewrite above imports it here)
    "azurik_mod/randomizer/live_link.py": ("LiveError",),
    # the maps' drawing (Step 4.2c3): the flights through the game's code under Unicorn (L2, a dev tool), the
    # generated data's extractor (db-extract: the data comes by this sync), the node types' capstone scan (the
    # names table holds them), the gallery's previews and the two scripts' files and command lines (the sdk and
    # the hosts keep the pictures, tools/randomizer/art/)
    "azurik_mod/randomizer/draft/envelope.py": ("l2_xbe", "l2_flight"),
    "azurik_mod/randomizer/levels.py": ("extract", "write_generated"),
    "azurik_mod/xbr/nodes.py": ("scan_types",),
    "azurik_mod/xbr/draw.py": ("png_rgba", "_write", "write_preview", "draw_previews"),   # (PNGs: art.png)
    "scripts/render_level_maps.py": ("argparse", "sys", "png", "draw_detail", "main", "__main__"),
    "scripts/render_model_icons.py": ("argparse", "sys", "main", "__main__"),
}


def read_index(path: Path = ORACLE / "ORACLE.toml") -> dict[str, dict]:
    """``{family: {"tag", "commit", "files": {path: sha256}[, "exported": {path: sha256}]}}``; empty when there
    is no index."""
    return tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_index(index: dict[str, dict], path: Path = ORACLE / "ORACLE.toml") -> None:
    lines = ["# Written by scripts/oracle_sync.py, never by hand: tests/test_oracle.py checks every file of",
             "# tests/oracle/<family>/ against its sha256 here; <family>.exported holds a facts file's sha256",
             "# as Modkit exported it, before its build spans became sha256 and size; <family>.source each",
             "# file the sync installed in AzurKit's source (scripts/oracle_sync.py's SOURCES)."]
    for family in sorted(index):
        entry = index[family]
        lines += ["", f"[{family}]", f"tag = {json.dumps(entry['tag'])}", f"commit = {json.dumps(entry['commit'])}",
                  "", f"[{family}.files]"]
        lines += [f"{json.dumps(rel)} = {json.dumps(sha)}" for rel, sha in sorted(entry["files"].items())]
        for table in ("exported", "source", "art"):
            if rows := entry.get(table):
                lines += ["", f"[{family}.{table}]"]
                lines += [f"{json.dumps(rel)} = {json.dumps(sha)}" for rel, sha in sorted(rows.items())]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def tree_hashes(folder: Path) -> dict[str, str]:
    """``{posix path: sha256}`` of every file under ``folder`` (``{"": sha256}`` when it is a file)."""
    if folder.is_file():
        return {"": hashlib.sha256(folder.read_bytes()).hexdigest()}
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def source_hashes(family: str, root: Path = ROOT) -> dict[str, str]:
    """``{repository path: sha256}`` of every file under the family's
    :data:`SOURCES` folders in ``root`` (Python's ``__pycache__`` aside)."""
    return {f"{dst}/{rel}".rstrip("/"): sha for _, dst, _ in SOURCES.get(family, ())
            for rel, sha in tree_hashes(root / dst).items() if "__pycache__" not in rel.split("/")}


def _binds(node: ast.stmt) -> set[str]:
    if (isinstance(node, ast.If) and isinstance(node.test, ast.Compare)   # a script's command line: "__main__"
            and ast.unparse(node.test) in ("__name__ == '__main__'", '__name__ == "__main__"')):
        return {"__main__"}
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {node.name}
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return {alias.asname or alias.name.split(".")[0] for alias in node.names}
    targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
    return {n.id for t in targets for n in ast.walk(t) if isinstance(n, ast.Name)}


def port(rel: str, text: str) -> str:
    """Modkit's module ``rel`` as AzurKit holds it: each top-level statement
    :data:`DROPS` names for it taken out with the comment lines right above
    it and the blank lines after it, and from its ``__all__`` list, then
    :data:`REWRITES`. ValueError naming a statement DROPS names that isn't
    there (or binds more than it names) and each import of Modkit left."""
    drop, lines, cut = set(DROPS.get(rel, ())), text.splitlines(keepends=True), set()
    dropped = frozenset(drop)
    for node in ast.parse(text).body:
        if (_binds(node) == {"__all__"} and isinstance(node, ast.Assign) and isinstance(node.value, ast.List)
                and all(isinstance(e, ast.Constant) for e in node.value.elts)
                and dropped & {e.value for e in node.value.elts}):   # its names, less those DROPS takes out
            kept = ", ".join(json.dumps(e.value) for e in node.value.elts if e.value not in dropped)
            lines[node.lineno - 1] = textwrap.fill(kept, 119, initial_indent="__all__ = [", subsequent_indent=" " * 11,
                                                   break_long_words=False) + "]\n"
            cut.update(range(node.lineno, node.end_lineno))
            continue
        if not (names := _binds(node)) & drop:
            continue
        if names - drop:
            raise ValueError(f"{rel}:{node.lineno}: a statement DROPS takes out also binds {sorted(names - drop)}")
        drop -= names
        first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", ()))]) - 1
        while first and lines[first - 1].lstrip().startswith("#"):   # the comment that says what it is
            first -= 1
        end = node.end_lineno
        while end < len(lines) and not lines[end].strip():
            end += 1
        cut.update(range(first, end))
    if drop:
        raise ValueError(f"{rel}: no top-level statement binds {sorted(drop)} (DROPS names them): update DROPS")
    out = "".join(line for i, line in enumerate(lines) if i not in cut).rstrip("\n") + "\n"
    for old, new in REWRITES:
        out = out.replace(old, new)
    left = [f"{rel}:{node.lineno} imports {name}" for node in ast.walk(ast.parse(out))
            for name in ([a.name for a in node.names] if isinstance(node, ast.Import) else
                         [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            if name.split(".")[0] == "azurik_mod"]
    if left:
        raise ValueError("Modkit is still imported after REWRITES (port it, or add a rewrite): " + "; ".join(left))
    return out


def sources(clone: Path, family: str) -> dict[str, bytes]:
    """``{repository path: bytes}``: the files of the family's
    :data:`SOURCES` as AzurKit installs them, from Modkit's tracked files in
    ``clone`` (:data:`OWN` aside); ValueError from :func:`port`."""
    out = {}
    for src, dst, ported in SOURCES.get(family, ()):
        for rel in sorted(filter(None, _git(clone, "ls-files", "-z", "--", src).split("\0"))):
            if rel in OWN:
                continue
            data = (clone / rel).read_bytes()
            if ported and rel.endswith(".py"):
                data = port(rel, data.decode("utf-8")).encode("utf-8")
            out[dst + rel.removeprefix(src)] = data
    return out


PNG = (0x89504E470D0A1A0A).to_bytes(8, "big")   # a PNG's signature (the XBE holds one: no 8-byte literal of it)


def pixels(png: bytes) -> tuple[int, int, int, bytes]:
    """(width, height, channels, rows of pixels top to bottom) of an 8-bit
    RGB or RGBA PNG that isn't interlaced (Modkit's pictures);
    ValueError for another."""
    if png[:8] != PNG:
        raise ValueError("not a PNG")
    at, idat, head = 8, [], None
    while at < len(png):
        (n,), tag = struct.unpack_from(">I", png, at), png[at + 4:at + 8]
        body, at = png[at + 8:at + 8 + n], at + 12 + n
        if tag == b"IHDR":
            head = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat.append(body)
    if head is None or head[2] != 8 or head[3] not in (2, 6) or head[6] != 0:
        raise ValueError(f"a PNG that isn't 8-bit RGB or RGBA, not interlaced: {head}")
    w, h, c = head[0], head[1], 3 if head[3] == 2 else 4
    raw, stride, out, prev = zlib.decompress(b"".join(idat)), w * c, bytearray(), bytearray(w * c)
    for y in range(h):
        kind, row = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride if kind else 0):   # the five filters (Modkit writes the first, none)
            a, b = row[i - c] if i >= c else 0, prev[i]
            up_left = prev[i - c] if i >= c else 0
            if kind == 1:
                row[i] = (row[i] + a) & 0xFF
            elif kind == 2:
                row[i] = (row[i] + b) & 0xFF
            elif kind == 3:
                row[i] = (row[i] + (a + b) // 2) & 0xFF
            elif kind == 4:
                pa, pb, pc = abs(b - up_left), abs(a - up_left), abs(a + b - 2 * up_left)
                row[i] = (row[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else up_left)) & 0xFF
            elif kind:
                raise ValueError(f"a PNG row's filter {kind}")
        out += row
        prev = row
    return w, h, c, bytes(out)


def pixel_digest(w: int, h: int, c: int, rows: bytes) -> str:
    """A picture's digest: the sha256 of ``"<w>x<h>x<channels>\\n"`` and its
    pixels, rows top to bottom (AzurKit's drawings take it the same way,
    ``tools/randomizer/art.digest``)."""
    return hashlib.sha256(f"{w}x{h}x{c}\n".encode() + rows).hexdigest()


def art_hashes(clone: Path, family: str) -> dict[str, str]:
    """``{Modkit path: digest}`` of the pictures :data:`ART_FILES` names in
    ``clone`` (Modkit's tracked files): each PNG's :func:`pixel_digest`,
    each other file's sha256."""
    out = {}
    for folder in ART_FILES.get(family, ()):
        for rel in sorted(filter(None, _git(clone, "ls-files", "-z", "--", folder).split("\0"))):
            data = (clone / rel).read_bytes()
            out[rel] = pixel_digest(*pixels(data)) if rel.endswith(".png") else hashlib.sha256(data).hexdigest()
    return out


def digest_spans(path: Path) -> str:
    """Replace each build span of the facts file ``path`` (a hex string at
    ``patch_sites.<va>.new.<case>``) with ``{"sha256", "size"}`` of its bytes;
    returns the file's sha256 as it was."""
    raw = path.read_bytes()
    facts = json.loads(raw)
    for site in facts["patch_sites"].values():
        for case, hexed in site.get("new", {}).items():
            span = bytes.fromhex(hexed)
            site["new"][case] = {"sha256": hashlib.sha256(span).hexdigest(), "size": len(span)}
    path.write_text(json.dumps(facts, indent=1) + "\n", encoding="utf-8")
    return hashlib.sha256(raw).hexdigest()


def derive(family: str, clone: Path, folder: Path, env: dict[str, str]) -> None:
    """Write the family's :data:`DERIVED` files into its bundle ``folder``,
    from Modkit's ``clone``: ``swap.json`` from its facts, ``resources.json``
    from its builds (``scripts/modkit_resources.py``, run in the clone at
    nice 15; it stops the sync when a build isn't G3's recorded one)."""
    if family != "models":
        return
    facts = {release: (clone / rel).read_bytes() for release, rel in SWAP}
    swap = {release: json.loads(raw)["swap"] for release, raw in facts.items()}
    swap["from"] = {rel: hashlib.sha256(facts[release]).hexdigest() for release, rel in SWAP}
    (folder / "swap.json").write_text(json.dumps(swap, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    shutil.copy(ROOT / "scripts" / "modkit_resources.py", clone / "scripts" / "_azurkit_resources.py")
    subprocess.run(["nice", "-n", "15", "uv", "run", "--locked", "--directory", str(clone), "python",
                    "scripts/_azurkit_resources.py", str(folder / "resources.json"), "--bundle", str(folder)],
                   check=True, env=env)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def sync(modkit: Path, ref: str, tag: str, families: tuple[str, ...]) -> list[str]:
    """Export ``families`` from Modkit at ``ref`` and install them; returns the lines to print."""
    commit = _git(modkit, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()
    index, out = read_index(), []
    with tempfile.TemporaryDirectory(prefix="azurkit-oracle-") as scratch:
        clone, bundle = Path(scratch, "modkit"), Path(scratch, "bundle")
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(modkit), str(clone)], check=True)
        _git(clone, "checkout", "--quiet", "--detach", commit)
        env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "PYTHONPATH")}
        argv = ["uv", "run", "--locked", "--directory", str(clone), "python", "scripts/export_oracle.py", str(bundle),
                "--tag", tag, *(a for f in families for a in ("--family", f))]
        subprocess.run(argv, check=True, env=env)
        try:
            ported = {family: sources(clone, family) for family in families}
            art = {family: art_hashes(clone, family) for family in families}
        except ValueError as exc:
            raise SystemExit(f"nothing written: {exc}") from None
        for family in families:
            derive(family, clone, bundle / family, env)
        for family in families:
            meta = json.loads((bundle / family / "oracle.json").read_text(encoding="utf-8"))
            if meta["commit"] != commit or meta["dirty"]:
                raise SystemExit(f"{family}: the bundle is from {meta['commit']} (dirty: {meta['dirty']}), not {commit}")
            if old := index.get(family, {}).get("commit"):
                todo = _git(modkit, "log", "--oneline", f"{old}..{commit}", "--", *PATHS[family]).splitlines()
                out += [f"{family}: {len(todo)} Modkit commits since {old[:12]} touch its paths (the port's to-do):",
                        *(f"  {line}" for line in todo)]
            shutil.rmtree(ORACLE / family, ignore_errors=True)
            shutil.copytree(bundle / family, ORACLE / family)
            exported = {rel: digest_spans(ORACLE / family / rel) for rel in FACTS if (ORACLE / family / rel).exists()}
            for _, dst, _ in SOURCES.get(family, ()):
                if (ROOT / dst).is_file():
                    (ROOT / dst).unlink()
                shutil.rmtree(ROOT / dst, ignore_errors=True)
            for rel, data in ported[family].items():
                (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
                (ROOT / rel).write_bytes(data)
            index[family] = {"tag": tag, "commit": commit, "files": tree_hashes(ORACLE / family)}
            index[family] |= {"exported": exported} if exported else {}
            index[family] |= {"source": source_hashes(family)} if family in SOURCES else {}
            index[family] |= {"art": art[family]} if art.get(family) else {}
            out.append(f"{family}: {len(index[family]['files'])} files at {tag} ({commit[:12]})")
    write_index(index)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--modkit", type=Path, default=os.environ.get("AZURKIT_MODKIT"),
                    help="Modkit's checkout (default $AZURKIT_MODKIT)")
    ap.add_argument("--ref", required=True, help="the Modkit commit, branch or tag to export at")
    ap.add_argument("--tag", required=True, help="the Modkit tag the bundle is cut at (recorded)")
    ap.add_argument("--family", action="append", choices=FAMILIES, required=True)
    args = ap.parse_args(argv)
    if args.modkit is None:
        ap.error("--modkit or $AZURKIT_MODKIT names Modkit's checkout")
    for line in sync(args.modkit, args.ref, args.tag, tuple(dict.fromkeys(args.family))):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())

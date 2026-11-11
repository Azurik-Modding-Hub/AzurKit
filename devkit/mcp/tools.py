"""The azurik MCP server's 8 tools (D64's names; ``docs/MCP.md``), each a
plain function that answers ``{"success": true, "result": ...}`` or
``{"success": false, "error": "..."}``, never a raised exception:

- config.xbr by its own names: :func:`entity_list` and :func:`entity_get`
  (from a config.xbr file or an image's);
- :func:`xbr_edit`: a modded ``.xbr``, by the mods file's ``xbr``
  operations (``azurkit.edits.xbr``);
- :func:`pack_list`: the packs and their sliders (``sdk.catalog``);
- :func:`pack_build_iso` and :func:`rando_build_iso`: a build with packs, a
  mods file and a seed (``sdk.build``, the recipe the ``azurkit build``
  command makes of its flags);
- :func:`iso_extract` and :func:`iso_repack`: an image's files into a new
  folder, and a folder's edits packed into the vanilla image.

They run on the sdk and the engine, so a refusal is theirs, named (never
game bytes). Nothing is clamped (D23): a slider's track and a cell's range
are hints, and only a value its encoding can't hold is refused (NaN,
infinity; an int32 cell's range, D45). A tool that fails writes nothing
(D35), and none writes over its input or a vanilla image (D36).
"""

from __future__ import annotations

import contextlib
import functools
import hashlib
import inspect
import io
import os
import shutil
import types
from collections.abc import Callable
from pathlib import Path

from azurkit import cli, sdk
from azurkit.core import gate
from azurkit.core import iso as xiso   # a tool's parameter is named iso
from azurkit.core.xbr import Document
from azurkit.core.xbr.keyed import EMPTY, Table
from azurkit.edits import layer, xbr
from azurkit.tools import mods

CONFIG = "gamedata/config.xbr"
OPTIONS = ("settings", "share", "obsidian_cost", "enable", "disable", "params", "config_mod", "character", "spoiler")
""":func:`rando_build_iso`'s options: the randomizer's settings (``settings``,
a settings file's table, or ``share``, a share string; ``obsidian_cost``),
:func:`pack_build_iso`'s packs and mods file, the ``character`` the player
wears (a recipe's) and a ``spoiler`` file to write."""
SEED = "42"   # rando_build_iso's seed when it is given none (Modkit's randomize-full's)


def _tool(fn: Callable) -> Callable:
    """``fn`` (it raises a refusal) as a tool that answers in the envelope."""
    @functools.wraps(fn)
    def run(*args, **kwargs) -> dict:
        try:
            return {"success": True, "result": fn(*args, **kwargs)}
        except (OSError, ValueError, LookupError) as exc:   # the sdk's and the engine's refusals, named
            return {"success": False, "error": str(exc)}
        except Exception as exc:   # anything else, still in the envelope, named by its type
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    run.__signature__ = inspect.signature(fn, eval_str=True).replace(return_annotation=dict)
    return run


def _file(path: str, what: str) -> Path:
    found = Path(path)
    if not found.is_file():
        raise ValueError(f"{what}: no file {found}")
    return found


def _never_over(target: Path, *inputs: Path) -> None:
    """Refuse ``target`` where it is one of ``inputs`` or a vanilla image (D36)."""
    if not target.exists():
        return
    for given in inputs:
        if given.exists() and target.samefile(given):
            raise ValueError(f"{target}: it is the tool's input, which it never writes over")
    for release in gate.RELEASES:
        if (found := gate.find(release)) is not None and target.samefile(found):
            raise ValueError(f"{target}: it is the vanilla {release.label} image, which a tool never writes over")


def _write(target: Path, data: bytes) -> None:
    """``data`` to ``target``, whole or not at all (a part file renamed into place)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(f"{target.name}.{os.urandom(4).hex()}.part")
    try:
        part.write_bytes(data)
        os.replace(part, target)
    finally:
        part.unlink(missing_ok=True)


def _tables(path: str) -> dict[str, Table]:
    """config.xbr's keyed tables, from the config.xbr at ``path`` or the image's."""
    source = _file(path, "config_xbr")
    try:
        reader = xiso.Reader(source)
    except ValueError:   # no volume descriptor: an XBR itself
        return Document(source.read_bytes()).tables
    with reader as r:
        try:
            return Document(r.read(CONFIG)).tables
        except FileNotFoundError:
            raise ValueError(f"{source}: an image with no {CONFIG}") from None


def _table(tables: dict[str, Table], section: str) -> Table:
    if section not in tables:
        raise ValueError(f"config.xbr has no table {section!r} (its tables: {', '.join(sorted(tables))})")
    return tables[section]


def _column(table: Table, entity: str) -> int | None:
    """The column ``entity`` names, as a mods file's ``set`` finds it (D51:
    itself, else the one name equal to it case-blind with ``_`` read as a
    space; a name several columns share, its last), or ``None``;
    ``ValueError`` where it spells several names."""
    names = [name for name in table.cols if name]
    if entity not in names:
        def fold(name: str) -> str:
            return name.casefold().replace("_", " ")
        hits = sorted({name for name in names if fold(name) == fold(entity)})
        if len(hits) > 1:
            raise ValueError(f"config table {table.name}: entity {entity!r} spells several: "
                             f"{', '.join(map(repr, hits))}")
        if not hits:
            return None
        entity = hits[0]
    return table.column(entity)


def _values(table: Table, col: int) -> dict:
    """``{property: value}`` of every cell of the column that isn't empty."""
    return {prop: cell.value for row, prop in enumerate(table.rows)
            if (cell := table.cell(col, row)).kind != EMPTY}


@_tool
def entity_list(config_xbr: str, section: str | None = None) -> dict | list:
    """config.xbr's tables, or one table's entities.

    Args:
        config_xbr: a config.xbr file, or an image (its gamedata/config.xbr).
        section: a table's name. Without it: {table: its entity count} for
            every table; with it, the table's entity (column) names in file
            order.
    """
    tables = _tables(config_xbr)
    if section is None:
        return {name: len(table.cols) for name, table in tables.items()}
    return list(_table(tables, section).cols)


@_tool
def entity_get(config_xbr: str, entity: str, section: str | None = None) -> dict:
    """An entity's values (every cell of its column that isn't empty), in
    one table or in every table that has it.

    Args:
        config_xbr: a config.xbr file, or an image (its gamedata/config.xbr).
        entity: the entity (column) name, spelled as a mods file may
            (case-blind, ``_`` for a space; a name several columns share
            reads its last, as a mods file's set writes it).
        section: a table's name, to read only that table.
    Returns {section, entity, properties} for one table (entity in
    config.xbr's own spelling), else {entity, sections: {table:
    properties}} and, where the spelling names several columns of a table,
    "ambiguous": {table: why} (spell it exactly to read those).
    """
    tables = _tables(config_xbr)
    if section is not None:
        table = _table(tables, section)
        if (col := _column(table, entity)) is None:
            raise ValueError(f"config table {section} has no entity {entity!r}")
        return {"section": section, "entity": table.cols[col], "properties": _values(table, col)}
    found, ambiguous = {}, {}
    for name, table in tables.items():
        try:
            if (col := _column(table, entity)) is not None:
                found[name] = _values(table, col)
        except ValueError as exc:
            ambiguous[name] = str(exc)
    if not found:
        raise ValueError("; ".join(ambiguous.values()) or f"config.xbr has no entity {entity!r}")
    return {"entity": entity, "sections": found} | ({"ambiguous": ambiguous} if ambiguous else {})


@_tool
def xbr_edit(inp: str, out: str, ops: list) -> dict:
    """WRITE a modded .xbr: the mods file's xbr operations on one file.

    Each op is the mods file's (``azurkit.edits.xbr``) without its "file"
    (the file is inp):
      - {"op": "set", "table", "entity", "prop", "value"}, with "col" (a
        column's index, where several share the entity's name) and "fill"
        (true: an empty cell takes the value) optional: a keyed cell by its
        names (D51's spellings), a number into a number cell, text into a
        string cell;
      - {"op": "replace_bytes", "offset", "expected", "value"}: hex bytes at
        a file offset where the file holds "expected" (their hex, up to
        32 B, or {"sha256", "size"}).
    A number is any finite value, never clamped (D23), but what an int32
    cell can't hold (D45). They apply in order: an op a later one
    overwrites is dropped whole and listed in conflicts (D28). Any op that
    can't apply fails the call, naming it, and nothing is written (D35).

    Args:
        inp: the source .xbr file.
        out: the .xbr to write: not inp, not a vanilla image.
        ops: the operations.
    Returns {output_path, ops_applied, conflicts}.
    """
    source, target = _file(inp, "inp"), Path(out)
    _never_over(target, source)
    if not isinstance(ops, list) or not ops:
        raise ValueError("ops: a list of xbr operations ({op: set | replace_bytes, ...}), not empty")
    if named := [k for k, op in enumerate(ops, 1) if isinstance(op, dict) and "file" in op]:
        raise ValueError(f"xbr op {named[0]}: no file (the file is inp)")
    file = f"gamedata/{source.stem}.xbr"   # the name the ops' refusals give it
    ops = xbr.normalize([{**op, "file": file} if isinstance(op, dict) else op for op in ops])
    data = source.read_bytes()
    planned = xbr.plan(ops, types.SimpleNamespace(files={file: None}, label=source.name), {file: data})
    files, conflicts = layer.compose({file: data}, [planned])
    _write(target, bytes(files.get(file, data)))
    return {"output_path": str(target), "ops_applied": len(ops) - len(conflicts),
            "conflicts": [str(c) for c in conflicts]}


def _xbr_cells(pack: str) -> dict[str, dict]:
    """The config.xbr cell each of the pack's XBR sliders writes: ``{file,
    table, entity, prop}``, or ``{file, table}`` where it multiplies several."""
    return {s.name: {"file": s.file, "table": s.table} | ({"entity": s.entity, "prop": s.prop} if s.cells is None
                                                           else {})
            for s in mods.PACKS[pack].sites if isinstance(s, mods.XbrParametricEdit)}


@_tool
def pack_list(category: str | None = None, pack: str | None = None) -> list:
    """Every pack with its sliders, in their canonical order. No image needed.

    Args:
        category: a category's id, to list only its packs.
        pack: a pack's name, to list only it.
    Per pack (sdk.catalog's): name, description, category, default_on (a
    build starts with it), releases, requires and requires_why (the packs it
    needs in the same build), sliders. Per slider: name, label, default,
    min, max and step (the track: display hints only, never limits, D23),
    unit, description, vanilla (None where the image's XBE holds it), whole
    (the whole numbers it takes, or None) and logic_floor; a config.xbr
    slider also "xbr", the cell it writes ({file, table, entity, prop}; a
    multiplier of several cells, {file, table}).
    """
    found = sdk.catalog()
    packs = found["packs"]
    if category is not None:
        if category not in (ids := [c["id"] for c in found["categories"]]):
            raise ValueError(f"no category {category!r} (the categories: {', '.join(ids)})")
        packs = [p for p in packs if p["category"] == category]
    if pack is not None:
        if pack not in mods.PACKS:
            raise ValueError(f"no pack {pack!r} (the packs: {', '.join(mods.PACKS)})")
        packs = [p for p in packs if p["name"] == pack]
    listed = []
    for p in packs:
        cells = _xbr_cells(p["name"])
        listed.append(p | {"sliders": [s | ({"xbr": cells[s["name"]]} if s["name"] in cells else {})
                                       for s in p["sliders"]]})
    return listed


def _recipe(image: str, enable: list | None, disable: list | None, params: dict | None,
            config_mod: str | dict | None) -> tuple[dict, list[str]]:
    """The build's recipe as ``azurkit build`` makes it (``cli.recipe``): the
    packs on by default and ``enable``'s (with each pack they require), less
    ``disable``'s, or the mods file ``config_mod``'s with those moves, each
    slider ``params`` gives; and the lines saying what the moves added."""
    for what, names in (("enable", enable), ("disable", disable)):
        if names is not None and not (isinstance(names, list) and all(isinstance(n, str) for n in names)):
            raise ValueError(f"{what}: a list of pack names")
    if params is not None and not isinstance(params, dict):
        raise ValueError("params: {pack: {slider: value}}")
    given = None
    if config_mod is not None:
        if isinstance(config_mod, str) and os.path.isfile(config_mod):
            config_mod = Path(config_mod).read_bytes()
        given = sdk.read_mods(config_mod)
        if given.get("files"):   # D35: never built without the layer
            raise ValueError(f"config_mod: its files layer ({', '.join(e['path'] for e in given['files'])}) replaces "
                             "files a player picks (azurkit build --file); the MCP server picks none")
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        made = cli.recipe(image, list(enable or []), list(disable or []), True, (), given)
    for name, sliders in (params or {}).items():
        if name not in made["packs"]:
            raise ValueError(f"params: the build doesn't apply {name!r} (enable it)")
        if not isinstance(sliders, dict):
            raise ValueError(f"params: {name}'s are {{slider: value}}")
        made["packs"][name] |= sliders
    return made, said.getvalue().splitlines()


def _built(made: dict, out: str, settled: list[str]) -> tuple[dict, dict]:
    """``sdk.build``'s report, and the reply: a seed's verdict too, where a mods file or the tool gave one."""
    report = sdk.build(made, out)
    return report, {"output_path": report["out"], "region": report["release"], "sha256": report["sha256"],
                    "summary": {"packs_applied": list(made["packs"]), "layers": report["layers"],
                                "files_changed": sorted(report["result"]), "output_size_bytes": report["size"],
                                "conflicts": report["conflicts"], "notes": report["notes"], "settled": settled}} | (
        {"randomizer": report["randomizer"]} if "randomizer" in report else {})


@_tool
def pack_build_iso(iso: str, out: str, enable: list | None = None, params: dict | None = None,
                   config_mod: str | dict | None = None, disable: list | None = None) -> dict:
    """WRITE a build: the packs, then the mods file's edits, on the vanilla
    image (sdk.build; the order every build takes), never clamped.

    Args:
        iso: the vanilla image, either release (D27: a build reads only a
            vanilla image).
        out: the image to write: not iso, not a vanilla image.
        enable: packs to apply besides those on by default (pack_list's
            default_on); a pack they require comes too (summary.settled says
            so).
        params: {pack: {slider: value}} for packs the build applies; any
            finite value (D23).
        config_mod: a mods file (its path, its JSON text or the object; a
            share link too): its packs replace those on by default, and its
            xbr edits, seed and character come with it; one with a files
            layer (Replace files) is refused.
        disable: packs on by default to leave out; one both enabled and
            disabled is refused.
    Returns {output_path, region (the input's release), sha256 (the
    output's), summary: {packs_applied, layers, files_changed,
    output_size_bytes, conflicts (each overwrite a later layer won, D28),
    notes, settled}}, and randomizer (rando_build_iso's) when the mods file
    holds a seed. A refusal names the pack, slider or edit, and nothing is
    written (D35); with no pack left and no config_mod there is nothing to
    build, and the call fails.
    """
    made, settled = _recipe(iso, enable, disable, params, config_mod)
    if not made["packs"] and config_mod is None:
        raise ValueError("nothing to build: no pack is enabled and there is no config_mod")
    return _built(made, out, settled)[1]


@_tool
def rando_build_iso(iso: str, out: str, seed: str | int | None = None, options: dict | None = None) -> dict:
    """WRITE a randomized build: the seed's plan (its first layer), then the
    packs, the character and the mods file's edits (sdk.build), read back
    against the plan before anything is written.

    Args:
        iso: the vanilla image, either release.
        out: the image to write: not iso, not a vanilla image.
        seed: any text or a whole number (default "42"); the same seed and
            settings give the same plan on every host.
        options: the randomizer's "settings" (a settings file's table) or
            "share" (a share string, AZR-...), its "obsidian_cost" (any
            finite number), pack_build_iso's "enable", "disable", "params"
            and "config_mod", the "character" the player wears (a recipe's:
            {"species", "mode", ...}) and "spoiler" (a file to write the
            spoiler to: not iso, out or a vanilla image). Any other is
            refused by name.
    Returns pack_build_iso's reply and "randomizer": the verdict (seed,
    share, settings, plan (its sha256), attempt, sliders, obsidian_cost,
    logic_verified, why_not, conflicts: a placement a later layer changed
    leaves the logic unverified, as does any moved slider, D28, D1064).
    """
    if isinstance(seed, bool) or not isinstance(seed, (str, int, type(None))):
        raise ValueError(f"seed: text or a whole number, not {seed!r}")
    options = dict(options or {})
    if unknown := sorted(set(options) - set(OPTIONS), key=str):
        raise ValueError(f"options: no option {', '.join(map(repr, unknown))} (the options: {', '.join(OPTIONS)})")
    if spoiler := options.get("spoiler"):   # D36, refused before the build as Modkit's layer did
        if Path(spoiler).resolve() == Path(out).resolve():
            raise ValueError(f"spoiler {spoiler}: it is the output image itself")
        _never_over(Path(spoiler), Path(iso))
    made, settled = _recipe(iso, options.get("enable"), options.get("disable"), options.get("params"),
                            options.get("config_mod"))
    made["randomizer"] = {"seed": SEED if seed is None else str(seed)} | {
        key: options[key] for key in ("settings", "share", "obsidian_cost") if key in options}
    if "character" in options:
        made["character"] = options["character"]
    report, reply = _built(made, out, settled)
    if spoiler := options.get("spoiler"):
        try:
            # out by another spelling (a case-blind disk, macOS's /System/Volumes/Data firmlink), which the
            # string check before the build can't see: the spoiler would replace the image
            if Path(spoiler).exists() and Path(spoiler).samefile(report["out"]):
                raise ValueError(f"spoiler {spoiler}: it is the output image itself")
            _write(Path(spoiler), report["spoiler"].encode("utf-8"))
        except BaseException:   # D35: no image without its spoiler
            Path(report["out"]).unlink(missing_ok=True)
            raise
    return reply


@_tool
def iso_extract(iso: str, dest: str, only: list | None = None) -> dict:
    """WRITE an image's files under a new folder, in the image's own spelling.

    Args:
        iso: the image.
        dest: the folder to write: missing or empty (it is made), whole or
            not at all.
        only: image paths to write, files or folders, in any letter case
            (e.g. ["gamedata/config.xbr"]); by default every file. A path
            the image hasn't fails the call, naming it.
    Returns {iso, dest, files}.
    """
    source, target = _file(iso, "iso"), Path(dest)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError(f"dest {target}: not a missing or empty folder")
    if only is not None and not (isinstance(only, list) and all(isinstance(path, str) for path in only)):
        raise ValueError("only: a list of the image's paths")
    with xiso.Reader(source) as r:
        files = [e for e in r.entries() if not e.is_dir]
        if only:
            def under(entry: xiso.Entry, path: str) -> bool:   # the file, or a file in the folder, at path
                key, wanted = xiso.key(entry.path), xiso.key(path.strip("/"))
                return key == wanted or key.startswith(wanted + "/")
            if missing := [path for path in only if not any(under(e, path) for e in files)]:
                raise ValueError(f"not in the image: {', '.join(missing)}")
            files = [e for e in files if any(under(e, path) for path in only)]
        if unsafe := [e.path for e in files if any(xiso._UNSAFE.search(name) for name in e.path.split("/"))]:
            raise ValueError(f"names no host writes as a file of its own (AZ-216): {', '.join(unsafe)}")
        part = target.with_name(f"{target.name}.{os.urandom(4).hex()}.part")
        try:
            for entry in files:
                (path := part / entry.path).parent.mkdir(parents=True, exist_ok=True)
                with path.open("wb") as f:
                    for data in r.chunks(entry):
                        f.write(data)
            part.mkdir(parents=True, exist_ok=True)   # none written: the folder still made
            if target.exists():
                target.rmdir()
            os.replace(part, target)
        finally:
            shutil.rmtree(part, ignore_errors=True)
    return {"iso": str(source), "dest": str(target), "files": len(files)}


@_tool
def iso_repack(src: str, out: str, region: str | None = None) -> dict:
    """WRITE the vanilla image with a folder's edits: each file of src (a
    tree as iso_extract writes it) whose bytes differ from vanilla's in
    their place, the rest vanilla's; filelist.txt is derived (each replaced
    file's md5 and size, as the game's HDD cache reads it), so src's own is
    ignored. Dotfiles (.DS_Store) are skipped; any other file the image
    hasn't fails the call, naming it, with nothing written.

    Args:
        src: the folder.
        out: the image to write: not inside src, not a vanilla image nor
            beside one (D36's folder rule, as every build's).
        region: the release whose vanilla image is packed (usa or europe;
            default USA's when it is found, else Europe's), its build files
            checked (D27).
    Returns {src, out, region, sha256 (the output's), files_changed}.
    """
    tree, target = Path(src), Path(out)
    if not tree.is_dir():
        raise ValueError(f"src: no folder {tree}")
    if target.resolve().is_relative_to(tree.resolve()):
        raise ValueError(f"out {target}: inside src {tree}, which the tool never writes into")
    releases = {release.name: release for release in gate.RELEASES}
    if region is not None and region not in releases:
        raise ValueError(f"region {region!r}: usa or europe")
    release = releases[region] if region else next((r for r in gate.RELEASES if gate.find(r)), gate.USA)
    spelled = {xiso.key(path): path for path in release.files}
    changed, extra = {}, []
    for path in sorted(tree.rglob("*")):
        rel = path.relative_to(tree)
        if not path.is_file() or any(part.startswith(".") for part in rel.parts):
            continue   # dotfiles (Finder's .DS_Store) are the host's, not the image's
        name = spelled.get(xiso.key(rel.as_posix()))
        if name is None:
            extra.append(rel.as_posix())
        elif name != "filelist.txt" and hashlib.sha256(data := path.read_bytes()).hexdigest() != release.files[name][1]:
            changed[name] = data
    if extra:
        raise ValueError(f"not files of the vanilla {release.label} image: {', '.join(extra)}")
    if (vanilla := gate.find(release)) is None:
        raise ValueError(f"no {release.label} image: {gate.missing(release)}")
    gate.require_new_output(target, tree, vanilla)   # D36 as sdk.build's: not beside a vanilla image either
    gate.verify(vanilla, whole=False, releases=(release,))
    sha256 = xiso.pack(xiso.read(vanilla, files=changed), target)
    return {"src": str(tree), "out": str(target), "region": release.name, "sha256": sha256,
            "files_changed": sorted(changed)}


TOOLS = (entity_list, entity_get, xbr_edit, pack_list, pack_build_iso, rando_build_iso, iso_extract, iso_repack)

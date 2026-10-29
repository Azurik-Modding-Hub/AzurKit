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
copied verbatim, and its planner, writer, physics, movement and layer, each
module through :func:`port` (:data:`REWRITES`' imports, and the statements
:data:`DROPS` names taken out: what AzurKit's engine can't hold, a process
pool, Modkit's build objects). ORACLE.toml's ``source`` table keeps each installed file's
sha256, so a later Modkit fix arrives by the same sync, never by hand. A
module that still imports Modkit after its rewrites, or a statement DROPS
names that is gone, stops the sync before anything is written.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import tomllib
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
    "rando": ("azurik_mod/randomizer", "tests/goldens/rando_plans.json", "tests/goldens/rando_iso.json",
              "tests/goldens/pipelines.json", "tests/goldens/europe/pipelines.json", "tests/goldens/gui.json"),
    "models": ("azurik_mod/patches/player_model", "azurik_mod/patches/_player_character.py", "azurik_mod/assets"),
}


RANDO = "src/azurkit/tools/randomizer"
SOURCES = {   # Modkit's source a family's sync installs in AzurKit's: (Modkit's folder or file, AzurKit's, through port())
    "rando": (("azurik_mod/randomizer/data", f"{RANDO}/data", False),
              ("azurik_mod/randomizer/planner", f"{RANDO}/planner", True),
              *((f"azurik_mod/randomizer/{name}.py", f"{RANDO}/{name}.py", True)
                for name in ("writer", "physics", "movement", "layer")),
              ("azurik_mod/randomizer/draft/tiers.toml", f"{RANDO}/draft/tiers.toml", False)),   # physics reads it
}
OWN = frozenset({"azurik_mod/randomizer/planner/dbcache.py"})   # AzurKit's own instead: tools/randomizer/dbcache.py
REWRITES = (("from azurik_mod.randomizer.planner import dbcache", "from azurkit.tools.randomizer import dbcache"),
            ("azurik_mod.randomizer.", "azurkit.tools.randomizer."),
            ("from azurik_mod.xbr.nodes import", "from azurkit.core.xbr.nodes import"),
            ("from azurik_mod.xbr.toc_scan import", "from azurkit.core.xbr.nodes import"),
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
        for table in ("exported", "source"):
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
        except ValueError as exc:
            raise SystemExit(f"nothing written: {exc}") from None
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

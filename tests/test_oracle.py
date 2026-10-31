"""``tests/oracle/``, the bundle Modkit's ``scripts/export_oracle.py`` writes
for the rando family (every other family's truth is AzurKit's own,
``tests/goldens/``: the core's and the packs' since Step 4.12a, the
characters' since Step 4.12c): every file is the one
``scripts/oracle_sync.py`` installed, as is each file of Modkit's source it
installs in ours (the randomizer's data and planner), and installed again
from Modkit's history it keeps the import contracts."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.oracle_sync import (FAMILIES, ORACLE, PATHS, ROOT, SOURCES, install, port, read_index, source_hashes,
                                 sources, tree_hashes)


def test_every_oracle_file_is_the_one_the_sync_installed():
    """A hand edit, a missing or an extra file in a family's folder fails;
    each family's ``oracle.json`` (Modkit's index) agrees with ORACLE.toml;
    and each file the sync installed in our source (``SOURCES``) is as it
    was installed, none missing or added."""
    index = read_index()
    assert set(index) == set(FAMILIES)
    assert {p.name for p in ORACLE.iterdir() if p.is_dir()} == set(index)
    for family, entry in index.items():
        files = tree_hashes(ORACLE / family)
        assert files == entry["files"], family
        meta = json.loads((ORACLE / family / "oracle.json").read_text(encoding="utf-8"))
        assert (meta["family"], meta["tag"], meta["commit"], meta["dirty"]) == (
            family, entry["tag"], entry["commit"], False)
        assert {rel: m["sha256"] for rel, m in meta["files"].items()} == {
            rel: sha for rel, sha in files.items() if rel != "oracle.json"}
        assert source_hashes(family) == entry.get("source", {}), family
    assert set(SOURCES) <= set(index)


def test_the_sync_ports_a_modkit_module_by_its_rewrites_and_drops_or_names_what_it_cant(monkeypatch):
    """A ported module loses each top-level statement DROPS names (with the
    comment right above it, the blank lines after it and its name in
    ``__all__``) and has its imports rewritten; one that still imports
    Modkit, or a statement DROPS names that is gone, is named."""
    monkeypatch.setattr("scripts.oracle_sync.DROPS", {"m.py": ("threading", "pool")})
    source = ("import json\nimport threading\n\nfrom azurik_mod.randomizer.planner.solver import Logic\n\n\n"
              "def kept():\n    return 1\n\n\n# the pool\n@cache\ndef pool(n):\n    return n\n\n\ndef last():\n    return 2\n"
              '__all__ = ["kept",\n           "pool", "last"]\n')
    assert port("m.py", source) == ("import json\nfrom azurkit.tools.randomizer.planner.solver import Logic\n\n\n"
                                    "def kept():\n    return 1\n\n\ndef last():\n    return 2\n"
                                    '__all__ = ["kept", "last"]\n')
    with pytest.raises(ValueError, match=r"m\.py:1 imports azurik_mod\.patching\.registry"):
        port("m.py", "from azurik_mod.patching.registry import all_packs\n" + source)
    with pytest.raises(ValueError, match=r"no top-level statement binds \['pool'\]"):
        port("m.py", "import threading\n")
    monkeypatch.setattr("scripts.oracle_sync.DROPS", {"s.py": ("sys", "main", "__main__")})   # a script's command line
    assert port("s.py", "import sys\n\n\ndef draw():\n    return 1\n\n\ndef main():\n    return 0\n\n\n"
                        "if __name__ == \"__main__\":\n    sys.exit(main())\n") == "def draw():\n    return 1\n"


def test_a_tag_bumps_commit_list_covers_every_file_of_its_family():
    """Each file a family bundles from Modkit lies on one of the family's
    paths (``oracle_sync.PATHS``), so a Modkit commit that touches only it
    is on the next tag bump's to-do list."""
    off = [f"{family}: {rel}" for family, entry in read_index().items() for rel in entry["files"]
           if rel not in ("cases.json", "oracle.json")
           and not any(rel == p or rel.startswith(p + "/") for p in PATHS[family])]
    off += [f"{family}: {src}" for family, copies in SOURCES.items() for src, _, _ in copies
            if not any(src == p or src.startswith(p + "/") for p in PATHS[family])]
    off += [f"{family}: {rel}" for family, entry in read_index().items() for rel in entry.get("art", {})
            if not any(rel.startswith(p + "/") for p in PATHS[family])]
    assert off == []


def _modkit() -> Path:
    """Modkit's checkout, whose history the sync ports: ``$AZURKIT_MODKIT``,
    else ``Azurik_Modkit`` beside the main checkout."""
    if env := os.environ.get("AZURKIT_MODKIT"):
        return Path(env)
    common = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            capture_output=True, text=True, check=True).stdout.strip()
    return Path(common).parent.parent / "Azurik_Modkit"


def test_a_re_sync_at_each_familys_commit_imports_no_tool_from_another(tmp_path):
    """Each family's sources ported again from Modkit at the commit
    ORACLE.toml records (``sources()``, installed by ``install()`` in a copy
    of ``src/``) keep import-linter's contracts there: the rewrites are every
    family's, so none may send one tool's import into another tool (a rule
    for the maps sent the characters' TOC reader into the randomizer's,
    Step 4.2c3's late review)."""
    index, clone, src = read_index(), tmp_path / "modkit", tmp_path / "src"
    subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(_modkit()), str(clone)], check=True)
    shutil.copytree(ROOT / "src", src, ignore=shutil.ignore_patterns("__pycache__"))
    for family, copies in SOURCES.items():
        subprocess.run(["git", "-C", str(clone), "checkout", "--quiet", index[family]["commit"], "--",
                        *(path for path, _, _ in copies)], check=True)
        install(tmp_path, family, sources(clone, family))
    lint = ("import importlib.util, sys; from importlinter.cli import lint_imports; "   # on the copy's azurkit
            "assert importlib.util.find_spec('azurkit').origin.startswith(sys.argv[2]); "
            "sys.exit(lint_imports(config_filename=sys.argv[1], no_cache=True))")
    run = subprocess.run([sys.executable, "-c", lint, str(ROOT / "pyproject.toml"), str(src)], capture_output=True,
                         text=True, env=os.environ | {"PYTHONPATH": str(src)})
    assert run.returncode == 0, run.stdout + run.stderr

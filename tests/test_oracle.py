"""``tests/oracle/``, the bundle Modkit's ``scripts/export_oracle.py`` writes:
every file is the one ``scripts/oracle_sync.py`` installed, as is each file
of Modkit's source it installs in ours (the randomizer's data and planner),
and both vanilla images match the core family's manifests file by file,
through the gate."""

from __future__ import annotations

import json

import pytest

from azurkit.core import gate
from scripts.oracle_sync import FACTS, ORACLE, PATHS, SOURCES, port, read_index, source_hashes, tree_hashes


def test_every_oracle_file_is_the_one_the_sync_installed():
    """A hand edit, a missing or an extra file in a family's folder fails;
    each family's ``oracle.json`` (Modkit's index) agrees with ORACLE.toml,
    by the exported sha256 for a facts file, whose build spans are installed
    as sha256 and size only (D3); and each file the sync installed in our
    source (``SOURCES``) is as it was installed, none missing or added."""
    index = read_index()
    assert {"core", "packs"} <= set(index)
    assert {p.name for p in ORACLE.iterdir() if p.is_dir()} == set(index)
    for family, entry in index.items():
        files = tree_hashes(ORACLE / family)
        assert files == entry["files"], family
        meta = json.loads((ORACLE / family / "oracle.json").read_text(encoding="utf-8"))
        assert (meta["family"], meta["tag"], meta["commit"], meta["dirty"]) == (
            family, entry["tag"], entry["commit"], False)
        exported = entry.get("exported", {})
        assert {rel: m["sha256"] for rel, m in meta["files"].items()} == {
            rel: exported.get(rel, sha) for rel, sha in files.items() if rel != "oracle.json"}
        assert sorted(exported) == sorted(rel for rel in FACTS if rel in files), family
        for rel in exported:
            sites = json.loads((ORACLE / family / rel).read_text(encoding="utf-8"))["patch_sites"].values()
            spans = [span for site in sites for span in site.get("new", {}).values()]
            assert spans and all(set(span) == {"sha256", "size"} for span in spans), rel
        assert source_hashes(family) == entry.get("source", {}), family
    assert set(SOURCES) <= set(index)


def test_the_sync_ports_a_modkit_module_by_its_rewrites_and_drops_or_names_what_it_cant(monkeypatch):
    """A ported module loses each top-level statement DROPS names (with the
    comment right above it, the blank lines after it and its name in
    ``__all__``) and has its imports
    rewritten; one that still
    imports Modkit, or a statement DROPS names that is gone, is named."""
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


def test_a_tag_bumps_commit_list_covers_every_file_of_its_family():
    """Each file a family bundles from Modkit lies on one of the family's
    paths (``oracle_sync.PATHS``), so a Modkit commit that touches only it
    is on the next tag bump's to-do list."""
    off = [f"{family}: {rel}" for family, entry in read_index().items() for rel in entry["files"]
           if rel not in ("cases.json", "oracle.json")
           and not any(rel == p or rel.startswith(p + "/") for p in PATHS[family])]
    off += [f"{family}: {src}" for family, copies in SOURCES.items() for src, _, _ in copies
            if not any(src == p or src.startswith(p + "/") for p in PATHS[family])]
    assert off == []


@pytest.mark.parametrize("release", [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
                                     pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe],
                                                  id="europe")])
def test_each_vanilla_image_matches_its_oracle_manifest(release, request):
    """The gate's manifest is the oracle's, and every folder and file of the
    image is in it, by path, size and sha256 (``gate.verify``)."""
    name = {"usa": "vanilla_manifest.json", "europe": "europe_manifest.json"}[release.name]
    assert release.manifest.read_bytes() == (ORACLE / "core/azurik_mod/assets" / name).read_bytes()
    stamp = gate.verify(request.getfixturevalue(f"{release.name}_iso"))
    assert (stamp.release, stamp.whole) == (release, True)

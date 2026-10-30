"""G1, the pack goldens (``tests/goldens/packs.json`` and its Europe twin,
``scripts/record_goldens.py``'s), as the tests read them: each case of a
pack, its recipe, and the files it changes from vanilla with their sha256,
by their paths in the image.

A golden records ``default.xbe`` and each file the pack's layer writes, at
vanilla's sha256 where it leaves it so (an XBR pack's ``default.xbe``, a
default case's ``config.xbr``); a case here holds only the files it
changes. Europe's G1 has no case for a pack that writes only XBRs:
``config.xbr`` is the same file in both releases (PLAN §3's gap by
design), so the USA cases stand for it there."""

from __future__ import annotations

from typing import NamedTuple

from azurkit.core import gate
from azurkit.tools import mods
from scripts import record_goldens

GOLDENS = {"usa": "packs.json", "europe": "europe/packs.json"}
PATHS = {"config.xbr": "gamedata/config.xbr"}   # Modkit's name for a file -> its path in the image


class Case(NamedTuple):
    pack: str
    params: dict
    files: dict[str, str]   # each file it changes -> its sha256


def _cases(release: gate.Release, packs) -> dict[str, Case]:
    golden, recipes = record_goldens.recorded(GOLDENS[release.name]), record_goldens.cases(GOLDENS[release.name])
    out = {}
    for case, files in golden.items():
        if (recipe := recipes[case])["pack"] in packs:
            paths = {PATHS.get(name, name): sha for name, sha in files.items()}
            out[case] = Case(recipe["pack"], recipe["params"],
                             {path: sha for path, sha in paths.items() if sha != release.files[path][1]})
    return out


def cases(release: gate.Release) -> dict[str, Case]:
    """The release's G1 cases of the ported packs, by Modkit's case names."""
    out = _cases(release, mods.PACKS)
    if release is not gate.USA:
        held = {case.pack for case in out.values()}
        xbr_only = {name for name, pack in mods.PACKS.items() if name not in held and "default.xbe" not in pack.files()}
        out |= _cases(gate.USA, xbr_only)
    return out


def check(result: dict[str, str], case: Case, name: str) -> None:
    """A build of the case (its ``result``: each file it changed and its
    sha256) changed its files to their sha256 and no other file but
    ``filelist.txt``."""
    assert {file: result.get(file) for file in case.files} == case.files, name
    assert result.keys() - {"filelist.txt"} == case.files.keys(), name

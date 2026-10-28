"""G1, the oracle's pack goldens (Modkit's ``tests/goldens/packs.json`` and
its Europe twin), as AzurKit's tests read them: each case of a ported
pack, its recipe, and the files it changes from vanilla with their sha256,
by their paths in the image.

Modkit records each file a pack reads, at vanilla's sha256 where the pack
leaves it so (an XBR pack's ``default.xbe``, a default case's
``config.xbr``); a case here holds only the files it changes. Europe's G1
has no case for a pack that writes only XBRs: ``config.xbr`` is the same
file in both releases (PLAN §3's gap by design), so the USA cases stand
for it there."""

from __future__ import annotations

import json
from typing import NamedTuple

from azurkit.core import gate
from azurkit.tools import mods
from scripts import gen_facts

GOLDENS = {"usa": "tests/goldens/packs.json", "europe": "tests/goldens/europe/packs.json"}
PATHS = {"config.xbr": "gamedata/config.xbr"}   # Modkit's name for a file -> its path in the image


class Case(NamedTuple):
    pack: str
    params: dict
    files: dict[str, str]   # each file it changes -> its sha256


def _oracle(rel: str) -> dict:
    return json.loads((gen_facts.ORACLE / "packs" / rel).read_text(encoding="utf-8"))


def _cases(release: gate.Release, packs) -> dict[str, Case]:
    golden, recipes = _oracle(GOLDENS[release.name]), _oracle("cases.json")[GOLDENS[release.name]]
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

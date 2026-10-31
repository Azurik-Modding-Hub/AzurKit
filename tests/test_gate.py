"""The gate (``azurkit.core.gate.verify``, D27) and ``azurkit verify``: an
image is a release's vanilla one when its files match that release's
manifest, and otherwise the first file that differs is named. These run on
synthetic images and releases (``tests/_xiso.py``: no game bytes), and the
two vanilla images through the gate, whole."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import types
from pathlib import Path

import pytest

from azurkit import cli, sdk
from azurkit.core import gate
from tests._xiso import fill, image

VANILLA = {"default.xbe": fill("xbe", 3000), "filelist.txt": fill("f", 40), "gamedata/a.xbr": fill("a", 100),
           "gamedata/b.xbr": fill("b", 5000), "movies/m.bik": fill("m", 70)}


def _release(tmp_path, name: str, files: dict[str, bytes], dirs=("gamedata", "movies")) -> gate.Release:
    manifest = tmp_path / f"{name}.json"
    manifest.write_text(json.dumps({"dirs": list(dirs), "files": {
        p: [len(data), hashlib.sha256(data).hexdigest()] for p, data in files.items()}}), encoding="utf-8")
    return dataclasses.replace(gate.USA, name=name, label=name.title(), manifest=manifest)


def test_the_gate_names_the_release_or_the_first_file_that_differs(tmp_path):
    """The release is the one whose ``default.xbe`` the image holds, else
    the one whose folders it has, else the first; a missing, extra, resized
    or changed file is named, the first in path order; a stamp for a build
    checks only the files a build reads."""
    other = _release(tmp_path, "other", VANILLA | {"default.xbe": fill("XBE", 3000)}, ("gamedata", "movies", "saves"))
    test = _release(tmp_path, "test", VANILLA)
    src = tmp_path / "in.iso"

    def verify(files: dict[str, bytes], whole: bool = True) -> gate.Stamp:
        src.write_bytes(image(files))
        return gate.verify(src, whole=whole, releases=(other, test))

    stamp = verify(VANILLA)
    assert (stamp.release, stamp.path, stamp.size, stamp.whole) == (test, src, src.stat().st_size, True)
    assert verify(VANILLA | {"movies/m.bik": fill("M", 70)}, whole=False).release == test
    with pytest.raises(gate.NotVanillaError, match=r"filelist\.txt: its contents differ$"):
        verify(VANILLA | {"filelist.txt": fill("F", 40)}, whole=False)   # a build rewrites it
    gamedata = {p: d for p, d in VANILLA.items() if p != "gamedata/a.xbr"}
    for files, why in (
            (VANILLA | {"gamedata/b.xbr": fill("B", 5000), "movies/m.bik": fill("M", 70)},
             "Test image: gamedata/b.xbr: its contents differ"),
            (VANILLA | {"movies/m.bik": fill("M", 70)}, "Test image: movies/m.bik: its contents differ"),
            (VANILLA | {"gamedata/a.xbr": fill("a", 101)}, "Test image: gamedata/a.xbr: 101 B, where vanilla has 100 B"),
            (gamedata, "Test image: gamedata/a.xbr: missing"),
            (VANILLA | {"gamedata/c.xbr": b"c"}, "Test image: gamedata/c.xbr: not in the vanilla image"),
            (VANILLA | {"default.xbe": fill("x", 3000)}, "Test image: default.xbe: its contents differ"),
            ({p: d for p, d in VANILLA.items() if p != "movies/m.bik"} | {"default.xbe": fill("x", 3000)},
             "Other image: default.xbe: its contents differ")):
        with pytest.raises(gate.NotVanillaError) as refused:
            verify(files)
        assert str(refused.value) == f"{src} is not the vanilla {why}"


def test_an_image_is_checked_once_until_it_changes_and_a_hosts_store_vouches_for_it_across_launches(tmp_path,
                                                                                                    monkeypatch):
    """Every sdk call on an image shares one check of its build files
    (``sdk._stamp``) until the image changes (its size, modification or
    change time), when it is checked again. With a host's store
    (``gate.STAMPS``) a later launch reads none of it, and an image changed
    since is checked, and refused, as any other."""
    monkeypatch.setattr(gate, "RELEASES", (_release(tmp_path, "test", VANILLA),))
    monkeypatch.setattr(sdk, "_STAMPS", {})
    hashed, sha256 = [], gate._sha256
    monkeypatch.setattr(gate, "_sha256", lambda r, entry: hashed.append(entry.path) or sha256(r, entry))
    src = tmp_path / "in.iso"
    src.write_bytes(image(VANILLA))
    first = sdk._stamp(str(src))
    once = len(hashed)
    assert once and sdk._stamp(str(src)) is first and len(hashed) == once
    os.utime(src, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns + 1))
    assert sdk._stamp(str(src)).mtime_ns == first.mtime_ns + 1 and len(hashed) == 2 * once
    kept = {}
    monkeypatch.setattr(gate, "STAMPS", types.SimpleNamespace(get=kept.get, put=kept.__setitem__))
    for launch in range(2):
        sdk._STAMPS.clear()
        assert sdk._stamp(str(src)).release.name == "test" and len(hashed) == 3 * once and len(kept) == 1
    src.write_bytes(image(VANILLA | {"gamedata/a.xbr": fill("A", 100)}))
    sdk._STAMPS.clear()
    with pytest.raises(gate.NotVanillaError, match=r"gamedata/a\.xbr: its contents differ$"):
        sdk._stamp(str(src))


def test_verify_and_build_refuse_an_image_that_isnt_vanilla_in_one_line(tmp_path, capsys, monkeypatch):
    """``azurkit verify`` and ``azurkit build`` name why an image isn't a
    release's vanilla one in one line and exit 1; the build writes
    nothing (D27, D35). ``azurkit verify`` with no ``--iso`` also exits 1
    when a release's image is missing, and says why."""
    src, out = tmp_path / "in.iso", tmp_path / "out.iso"
    src.write_bytes(image({"default.xbe": fill("x", 20)}))
    assert cli.main(["verify", "--iso", str(src)]) == 1
    err = capsys.readouterr().err
    assert err.startswith(f"azurkit: {src} is not the vanilla USA image: ") and err.count("\n") == 1
    assert cli.main(["build", "--iso", str(src), "--out", str(out)]) == 1
    assert capsys.readouterr().err == (f"azurkit: {src} is not the vanilla USA image: default.xbe: 20 B, where "
                                       f"vanilla has {gate.USA.files['default.xbe'][0]:,} B\n")
    assert not out.exists()
    monkeypatch.setattr(gate, "verify", lambda path, **_: gate.Stamp(gate.USA, Path(path), 0, 0, True))
    monkeypatch.setenv("AZURKIT_ISO", str(src))
    monkeypatch.setenv("AZURKIT_ISO_EUROPE", str(out))
    assert cli.main(["verify"]) == 1
    assert capsys.readouterr().err == f"azurkit: no Europe image: AZURKIT_ISO_EUROPE names no file ({out})\n"


@pytest.mark.parametrize("release", [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
                                     pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe],
                                                  id="europe")])
def test_each_vanilla_image_matches_its_manifest_file_by_file(release, request):
    """Every folder and file of each release's vanilla image is in its
    manifest (``core/manifests/<release>.json``, AzurKit's own since Step
    4.12a), by path, size and sha256, and nothing else is (``gate.verify``,
    whole)."""
    stamp = gate.verify(request.getfixturevalue(f"{release.name}_iso"))
    assert (stamp.release, stamp.whole) == (release, True)

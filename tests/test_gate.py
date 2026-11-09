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
    hashed, sha256, digests = [], gate._sha256, sdk._digests
    monkeypatch.setattr(gate, "_sha256", lambda r, entry: hashed.append(entry.path) or sha256(r, entry))
    monkeypatch.setattr(sdk, "_digests", lambda path, steps: hashed.extend(found := digests(path, steps)) or found)
    src = tmp_path / "in.iso"
    src.write_bytes(image(VANILLA))
    first = sdk._stamp(str(src))
    once = len(hashed)
    assert once and sdk._stamp(str(src)) is first and len(hashed) == once
    os.utime(src, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns + 1000))   # NTFS keeps 100 ns
    assert sdk._stamp(str(src)).mtime_ns == first.mtime_ns + 1000 and len(hashed) == 2 * once
    kept = {}
    monkeypatch.setattr(gate, "STAMPS", types.SimpleNamespace(get=kept.get, put=kept.__setitem__))
    for launch in range(2):
        sdk._STAMPS.clear()
        assert sdk._stamp(str(src)).release.name == "test" and len(hashed) == 3 * once and len(kept) == 1
    src.write_bytes(image(VANILLA | {"gamedata/a.xbr": fill("A", 100)}))
    sdk._STAMPS.clear()
    with pytest.raises(gate.NotVanillaError, match=r"gamedata/a\.xbr: its contents differ$"):
        sdk._stamp(str(src))


def test_verify_every_file_is_kept_by_the_stamp(tmp_path, monkeypatch):
    """Every file checked after a build's check of the image as it is now
    (``kept``: the image picked) hashes only the files that check left, its
    progress from 0 to their bytes; its stamp is whole, and a check after it,
    of every file or a build's, hashes nothing, also by a host's store
    (``gate.STAMPS``) in a later launch. A file the build's check left that
    differs is named; a touched image is checked again, every file."""
    test = _release(tmp_path, "test", VANILLA)
    hashed, sha256 = set(), gate._sha256
    monkeypatch.setattr(gate, "_sha256", lambda r, entry: hashed.add(entry.path) or sha256(r, entry))
    src = tmp_path / "in.iso"
    src.write_bytes(image(VANILLA))
    builds = {p for p in VANILLA if p.startswith(gate.BUILD_FILES)}

    def verify(**given) -> gate.Stamp:
        hashed.clear()
        return gate.verify(src, releases=(test,), **given)

    build = verify(whole=False)
    assert not build.whole and hashed == builds
    ticks = []
    whole = verify(kept=build, progress=lambda done, total: ticks.append((done, total)))
    rest = len(VANILLA["movies/m.bik"])
    assert whole.whole and hashed == {"movies/m.bik"} and ticks == [(0, rest), (rest, rest)]
    assert verify(kept=whole) is whole and verify(whole=False, kept=whole) is whole and not hashed
    kept = {}
    monkeypatch.setattr(gate, "STAMPS", types.SimpleNamespace(get=kept.get, put=kept.__setitem__))
    assert verify(whole=False) == build and verify() == whole and hashed == {"movies/m.bik"}
    for asked in (True, False):   # a later launch: the store's stamp, whole
        assert verify(whole=asked) == whole and gate.vouched(src, whole=asked, releases=(test,)).whole
        assert not hashed
    os.utime(src, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns + 1000))   # NTFS keeps 100 ns
    assert verify(kept=whole).whole and hashed == set(VANILLA)
    src.write_bytes(image(VANILLA | {"movies/m.bik": fill("M", 70)}))
    with pytest.raises(gate.NotVanillaError, match=r"movies/m\.bik: its contents differ$"):
        verify(kept=verify(whole=False))
    assert hashed == {"movies/m.bik"}


def test_the_hosts_hashes_name_the_same_first_difference_and_a_wrong_one_is_refused_by_the_files_name(tmp_path,
                                                                                                        monkeypatch):
    """The check hashed on the sdk's threads (a CPython host's) or with a
    host's digests (the site's WebCrypto, ``sdk.layout`` and
    ``sdk.prime``) names the same first file that differs as the plain
    walk; a digest that isn't the file's is refused by its name, even after
    the right ones vouched for the path (the site's look-alike File)."""
    monkeypatch.setattr(gate, "RELEASES", (_release(tmp_path, "test", VANILLA),))
    monkeypatch.setattr(sdk, "_STAMPS", {})
    src = tmp_path / "in.iso"
    src.write_bytes(image(VANILLA | {"gamedata/b.xbr": fill("B", 5000)}))
    with pytest.raises(gate.NotVanillaError) as plain:
        gate.verify(src, whole=False, releases=gate.RELEASES)
    with pytest.raises(gate.NotVanillaError) as threaded:
        sdk._stamp(str(src))
    why = f"{src} is not the vanilla Test image: gamedata/b.xbr: its contents differ"
    assert str(plain.value) == str(threaded.value) == why
    src.write_bytes(image(VANILLA))
    files = sdk.layout(str(src))["files"]
    assert [f[0] for f in files] == ["default.xbe", "filelist.txt", "gamedata/a.xbr", "gamedata/b.xbr"]
    data = src.read_bytes()
    digests = {path: hashlib.sha256(data[at:at + size]).hexdigest() for path, at, size in files}
    for _ in range(2):   # a wrong digest refused, the right ones vouching, and the wrong one refused again
        with pytest.raises(gate.NotVanillaError, match=r"gamedata/a\.xbr: its contents differ$"):
            sdk.prime(str(src), digests | {"gamedata/a.xbr": "0" * 64})
        assert sdk.prime(str(src), digests) == {"release": "test", "label": "Test"}


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


def test_a_manifest_is_written_from_the_exact_vanilla_image_alone_and_the_gate_reads_it_back(tmp_path, monkeypatch,
                                                                                               capsys):
    """Step 4.24a (Modkit's ``iso-verify --write-manifest``): ``python -m devkit builds write-manifest`` writes a
    release's manifest from the image whose whole size and sha256 are that release's, in Modkit's layout (each
    folder, sorted, then each file's size and sha256 by path), and the gate passes the image against it; an image
    of another sha256 or size is refused by name, and nothing is written."""
    from devkit.builds import write_manifest

    data = image(VANILLA)
    src, other, out = tmp_path / "in.iso", tmp_path / "other.iso", tmp_path / "elsewhere.json"
    src.write_bytes(data)
    other.write_bytes(image(VANILLA | {"movies/m.bik": fill("M", 70)}))
    test = dataclasses.replace(_release(tmp_path, "test", {}), iso_sha256=hashlib.sha256(data).hexdigest(),
                               iso_size=len(data))
    monkeypatch.setattr(gate, "RELEASES", (test,))
    assert write_manifest.main(["--iso", str(src)]) == 0
    assert capsys.readouterr().out == f"{src}: the vanilla Test image; wrote its 7 entries to {test.manifest}\n"
    rows = ",\n".join(f'  "{p}": [{len(d)}, "{hashlib.sha256(d).hexdigest()}"]' for p, d in sorted(VANILLA.items()))
    assert test.manifest.read_text(encoding="utf-8") == (
        f'{{\n "dirs": ["gamedata", "movies"],\n "files": {{\n{rows}\n }}\n}}\n')
    gate._manifest.cache_clear()
    assert gate.verify(src, releases=(test,)).release == test
    for given, why in ((other, f"{len(data):,} B, Test's size, but its sha256 is "),
                       (tmp_path / "test.json", f"{test.manifest.stat().st_size:,} B, where Test's is {len(data):,} B")):
        assert write_manifest.main(["--iso", str(given), "--out", str(out)]) == 1
        assert capsys.readouterr().err.startswith(f"write-manifest: {given} is no release's vanilla image: {why}")
        assert not out.exists()


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

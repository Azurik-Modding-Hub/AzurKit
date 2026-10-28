"""The XISO reader and packer (``azurkit.core.iso``, ``core.filelist``) and
the identity build.

The packer's pins run on synthetic images (``tests/_xiso.py``: no game
bytes); the identity build reads each release's vanilla image."""

from __future__ import annotations

import _thread
import hashlib
import struct
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from azurkit import cli
from azurkit.core import filelist, gate, iso
from tests._xiso import S, fill, image


def _sha256(path) -> str:
    with open(path, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def test_a_file_that_fits_is_written_in_place_and_one_that_outgrows_its_sectors_moves_past_the_end(tmp_path):
    """D30: the layout is kept. A replaced file that fits its sectors stays
    in them; ones that outgrow them move past the image's end, in path
    order whatever order they come in, and the image is padded to 64 KiB.
    Every other entry keeps its sector and every file reads back. The
    segments cover the image once, in order: the replaced bytes once each,
    the rest copied from the input or zeros past its end. A build never
    writes over its input (D36), and pack returns the sha256 of what it
    wrote."""
    old = {"a.bin": fill("a", 90), "gamedata/big.xbr": fill("big", 3 * S), "gamedata/sub/c.xbr": fill("c", 100),
           "z.bin": fill("z", 10)}
    src = tmp_path / "in.iso"
    src.write_bytes(image(old))
    new = {"A.BIN": fill("A", 2000), "gamedata/sub/c.xbr": fill("C", 5000), "gamedata/big.xbr": fill("B", 3 * S + 1)}
    built = iso.read(src, new)
    assert iso.read(src, dict(reversed(new.items()))).sha256() == built.sha256()
    with pytest.raises(ValueError, match="the build's input"):
        iso.pack(built, src)
    out = tmp_path / "out.iso"
    assert iso.pack(built, out) == _sha256(out) == built.sha256()
    data, end = out.read_bytes(), src.stat().st_size // S
    pieces = built.segments()
    assert b"".join(bytes(p.data) if isinstance(p, iso.Bytes) else data[p.offset:p.offset + p.size]
                    if isinstance(p, iso.Copy) else bytes(p.size) for p in pieces) == data
    assert all(p.offset + p.size <= src.stat().st_size for p in pieces if isinstance(p, iso.Copy))
    assert sum(p.size for p in pieces if isinstance(p, iso.Bytes)) == 3 * 8 + 2000 + 5000 + 3 * S + 1
    with iso.Reader(src) as r:
        before = {e.path: e.sector for e in r.entries()}
    with iso.Reader(out) as r:
        after = {e.path: e.sector for e in r.entries()}
        assert {p: r.read(p) for p in old} == old | {"a.bin": new["A.BIN"]} | {p: new[p] for p in new if p in old}
    assert after.keys() == before.keys()
    assert {p: s for p, s in after.items() if s != before[p]} == {"gamedata/big.xbr": end,
                                                                  "gamedata/sub/c.xbr": end + 4}
    assert len(data) % 0x10000 == 0


def _listing(files: dict[str, bytes]) -> bytes:
    """A ``filelist.txt`` as vanilla's is laid out, for the three gamedata
    files of ``files``: CRLF lines, a scope line per folder, sizes
    right-aligned in 8 columns."""
    def row(path: str) -> str:
        return f"f {hashlib.md5(files[path]).hexdigest()} {len(files[path]):8d} {path.rpartition('/')[2]}\r\n"
    return ("\\\r\n" + row("gamedata/config.xbr") + "d index\r\n" + row("gamedata/loc.xbr")
            + "\r\n\\index\\\r\n" + row("gamedata/index/index.xbr") + "\r\n").encode()


def test_a_build_rewrites_the_filelist_lines_of_the_files_it_changes_and_of_stale_ones(tmp_path):
    """The game re-copies a cached file only when its ``filelist.txt`` line
    changes (xemu, 2026-10-09), so a build puts each changed file's md5 and
    size in its line, case-blind, its size right-aligned; a line that lists
    a file at another size than its own (vanilla Europe has three) gets the
    file's own; an unlisted file changes nothing, and an explicit
    ``filelist.txt`` gets the same rewrite. With no edits the image is its
    input, stale lines and all. A line whose size isn't decimal digits
    lists no file."""
    old = {"english.txt": fill("english", 90), "gamedata/config.xbr": fill("config", 5000),
           "gamedata/loc.xbr": fill("loc", 60), "gamedata/index/index.xbr": fill("index", 3000)}
    stale = _listing(old | {"gamedata/loc.xbr": fill("stale", 61)})
    src = tmp_path / "in.iso"
    src.write_bytes(image(old | {"filelist.txt": stale}))
    assert iso.read(src).sha256() == _sha256(src)
    new = old | {"english.txt": fill("ENGLISH", 90), "gamedata/config.xbr": fill("CONFIG", 5000),
                 "gamedata/index/index.xbr": fill("index", 70000)}
    files = {"english.txt": new["english.txt"], "gamedata/config.xbr": new["gamedata/config.xbr"],
             "GAMEDATA/Index/INDEX.XBR": new["gamedata/index/index.xbr"]}
    for explicit in ({}, {"FileList.txt": stale}):
        out = tmp_path / "out.iso"
        iso.pack(iso.read(src, files | explicit), out)
        with iso.Reader(out) as r:
            assert r.read("filelist.txt") == _listing(new), explicit
    assert filelist.rows(b"f 00 \xb2 a.xbr\r\nf 00 7 b.xbr\r\n") == [filelist.Row(1, "gamedata/b.xbr", "00", 7)]


def test_an_image_the_kernel_would_trip_on_is_refused_before_anything_is_written(tmp_path):
    """D35: a truncated image (a file or a table cut off by its end), a
    folder whose record points back at the root's table, and a table whose
    search tree links back to a record are each refused by name, never
    built and never walked forever."""
    sound = image({"a.bin": fill("a", 10), "d/x.bin": fill("x", 3000), "d/y.bin": fill("y", 10)})
    src = tmp_path / "in.iso"
    src.write_bytes(sound)
    with iso.Reader(src) as r:
        d, y = r.find("d"), r.find("d/y.bin")
    cycle, loop = bytearray(sound), bytearray(sound)
    struct.pack_into("<I", cycle, d.record + 4, 33)                     # d's table is the root's
    struct.pack_into("<H", loop, y.record, y.record % S // 4)           # y's left link: y itself
    for broken, why in ((sound[:y.sector * S + 5], "d/y.bin: it runs past the end of the image"),
                        (sound[:d.sector * S + 10], "d: its table runs past the end of the image"),
                        (cycle, "d: a folder cycle"), (loop, f"d: a link back to record {y.record % S}")):
        src.write_bytes(broken)
        with pytest.raises(ValueError, match=why):
            iso.pack(iso.read(src), tmp_path / "out.iso")
        assert not (tmp_path / "out.iso").exists()


RELEASES = [pytest.param(gate.USA, marks=pytest.mark.vanilla, id="usa"),
            pytest.param(gate.EUROPE, marks=[pytest.mark.vanilla, pytest.mark.europe], id="europe")]


@pytest.mark.parametrize("release", RELEASES)
def test_an_identity_build_is_the_vanilla_image_and_starts_no_thread(release, request, tmp_path, monkeypatch, capsys):
    """pack(read(v)) is v, byte for byte, for each release: ``azurkit build``
    checks the files a build reads (D27), then writes the image with no
    edits. The build path starts no thread (the web page's worker has none;
    Modkit's gate hashed on 8), which the guard here would refuse."""
    def refuse(*args, **kwargs):
        raise AssertionError("the build path started a thread")
    for owner, name in ((threading.Thread, "start"), (threading, "_start_joinable_thread"),
                        (_thread, "start_new_thread"), (_thread, "start_joinable_thread")):
        monkeypatch.setattr(owner, name, refuse)
    with pytest.raises(AssertionError, match="started a thread"):
        ThreadPoolExecutor(1).submit(int)
    source, out = request.getfixturevalue(f"{release.name}_iso"), tmp_path / f"{release.name}.out"
    try:
        assert cli.main(["build", "--iso", str(source), "--out", str(out)]) == 0
        written = _sha256(out)
    finally:
        out.unlink(missing_ok=True)
    assert written == release.iso_sha256
    assert capsys.readouterr().out.endswith(f"{release.label}, {release.iso_size:,} B, sha256 {written}\n")

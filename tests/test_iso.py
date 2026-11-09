"""The XISO reader and packer (``azurkit.core.iso``, ``core.filelist``), the
identity build, and the root entries a build adds.

The packer's pins run on synthetic images (``tests/_xiso.py``: no game
bytes); the identity build and the root entries read each release's vanilla
image."""

from __future__ import annotations

import _thread
import ctypes
import hashlib
import os
import re
import stat
import struct
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from azurkit import cli, sdk
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
    wrote, reporting its progress (first before it makes its part file);
    an exception the progress callback raises cancels the write and leaves
    nothing behind; given a host's ``sha256()``, it returns that, and once
    the input has changed since it was read it writes nothing."""
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
    seen = []
    assert iso.pack(built, out, progress=lambda *done: seen.append(done)) == _sha256(out) == built.sha256()
    assert (seen[0], seen[-1]) == ((0, built.size), (built.size, built.size))   # the first before the .part

    def cancel(done, total):
        raise KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        iso.pack(built, tmp_path / "cancelled.iso", progress=cancel)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["in.iso", "out.iso"]
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
    assert iso.pack(built, tmp_path / "given.iso", sha256=lambda: "given") == "given"   # a host's hash, from Build on
    assert _sha256(tmp_path / "given.iso") == built.sha256() == iso.digest(built)
    os.utime(src, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns + 1000))   # NTFS keeps 100 ns
    with pytest.raises(ValueError, match="it changed after the build read it"):   # D27: the input as the build read it
        iso.pack(built, tmp_path / "late.iso")
    assert not (tmp_path / "late.iso").exists()


def _xattrs(path, name: str | None = None) -> list[str]:
    """The extended attributes' names of the file at ``path``, after
    setting ``name`` on it (Windows has none)."""
    if os.name == "nt":
        return []
    if sys.platform != "darwin":
        if name:
            os.setxattr(path, f"user.{name}", b"1")
        return os.listxattr(path)
    libc = ctypes.CDLL(None, use_errno=True)
    if name:
        assert libc.setxattr(os.fsencode(path), name.encode(), b"1", 1, 0, 0) == 0
    names = ctypes.create_string_buffer(4096)
    size = libc.listxattr(os.fsencode(path), names, 4096, 0)
    return [n.decode() for n in names.raw[:max(size, 0)].split(b"\0") if n]


def test_a_clone_of_the_input_and_the_streamed_copy_write_the_same_image_as_a_fresh_file(tmp_path, monkeypatch):
    """pack clones the input where its file system can (this Mac's APFS) and
    writes only the image's writes over the clone; where the clone fails
    (another volume) it streams the whole image. Either way the bytes and
    the sha256 are the same, and the file a fresh one's: its mode, and none
    of the input's extended attributes (its quarantine flag, say) or flags
    (Finder's Locked: a locked image saves as an unlocked one did), and a
    transparently compressed input (``ditto --hfsCompression``) saves its
    own bytes."""
    src = tmp_path / "in.iso"
    src.write_bytes(image({"a.bin": fill("a", 90), "gamedata/big.xbr": fill("big", 3 * S), "z.bin": fill("z", 10)}))
    mac = sys.platform == "darwin"
    if mac:   # compressed on disk (decmpfs), as a space-saving tool leaves it
        raw = src.rename(tmp_path / "raw.iso")
        subprocess.run(["ditto", "--hfsCompression", str(raw), str(src)], check=True, timeout=60)
        raw.unlink()
        assert src.stat().st_flags & stat.UF_COMPRESSED
    _xattrs(src, "com.azurkit.test")
    src.chmod(0o444)   # the player's image, read-only
    if mac:
        os.chflags(src, src.stat().st_flags | stat.UF_IMMUTABLE)   # and locked in Finder
    try:
        built = iso.read(src, {"a.bin": fill("A", 50), "gamedata/big.xbr": fill("B", 3 * S + 1)})
        clones, clone = [], iso._clone
        monkeypatch.setattr(iso, "_clone", lambda source, part: clones.append(fd := clone(source, part)) or fd)
        cloned, streamed = tmp_path / "cloned.iso", tmp_path / "streamed.iso"
        sha = iso.pack(built, cloned)
        assert clones[0] is not None or not mac
        monkeypatch.setattr(iso, "_clone", lambda source, part: None)
        assert iso.pack(built, streamed) == sha == built.sha256() == _sha256(cloned) == _sha256(streamed)
        assert cloned.read_bytes() == streamed.read_bytes() and _xattrs(cloned) == []
        assert stat.S_IMODE(cloned.stat().st_mode) == stat.S_IMODE(streamed.stat().st_mode)
        assert not mac or cloned.stat().st_flags == streamed.stat().st_flags == 0
        assert sorted(p.name for p in tmp_path.iterdir()) == ["cloned.iso", "in.iso", "streamed.iso"]
    finally:
        if mac:
            os.chflags(src, src.stat().st_flags & ~stat.UF_IMMUTABLE)   # tmp_path's cleanup can't remove a locked file


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
    checks the files a build reads (D27), then, with no pack (``--no-defaults``),
    writes the image with no edits. With the sdk's threads off (a CPython host hashes the check on them),
    the build path starts no thread (the web page's worker has none), which the guard here would refuse."""
    monkeypatch.setattr(sdk, "THREADS", False)

    def refuse(*args, **kwargs):
        raise AssertionError("the build path started a thread")
    for owner, name in ((threading.Thread, "start"), (threading, "_start_joinable_thread"),
                        (_thread, "start_new_thread"), (_thread, "start_joinable_thread")):
        monkeypatch.setattr(owner, name, refuse)
    with pytest.raises(AssertionError, match="started a thread"):
        ThreadPoolExecutor(1).submit(int)
    source, out = request.getfixturevalue(f"{release.name}_iso"), tmp_path / f"{release.name}.out"
    try:
        assert cli.main(["build", "--iso", str(source), "--out", str(out), "--no-defaults"]) == 0
        written = _sha256(out)
    finally:
        out.unlink(missing_ok=True)
    assert written == release.iso_sha256
    assert capsys.readouterr().out.endswith(f"{release.label}, {release.iso_size:,} B, sha256 {written}\n")


@pytest.mark.parametrize("release", RELEASES)
def test_inserted_root_entries_read_back_and_vanilla_entries_keep_their_sectors(release, request):
    """``iso.read(..., add=)`` (Q66, V10: how a build carries /azurkit.json
    and /azurkit.bin): the new files go past the end, in name order, and the
    root folder's table is rebuilt in its one sector (USA's 208 B to 264,
    Europe's 284 to 340, its size in the volume descriptor): the image reads
    back with every vanilla entry at its sector and size and the new files'
    bytes. A name the root has, one no host may write and entries past the
    table's sector are refused, before anything is written (D35)."""
    path = request.getfixturevalue(f"{release.name}_iso")
    with iso.Reader(path) as r:
        before = {e.path: (e.sector, e.size) for e in r.entries()}
        table = r._root
    add = {"azurkit.json": b'{"format": "azurkit-manifest"}\n', "azurkit.bin": fill("bin", 3 * S + 5)}
    made = iso.read(path, None, add=add)
    with iso.Reader(made) as r:
        after = {e.path: (e.sector, e.size) for e in r.entries()}
        assert (table, r._root) == ((264, 208), (264, 264)) if release is gate.USA else ((264, 284), (264, 340))
        assert {name: r.read(name) for name in add} == add
    end = -(-release.iso_size // S)
    assert {k: v for k, v in after.items() if k not in before} == {"azurkit.bin": (end, 3 * S + 5),
                                                                    "azurkit.json": (end + 4, len(add["azurkit.json"]))}
    assert {k: after[k] for k in before} == before
    for given, error, why in (({"Default.XBE": b"x"}, FileExistsError, "Default.XBE: already in the image's root"),
                              ({"con.txt": b"x"}, ValueError, "'con.txt': not a name a root entry can hold"),
                              ({f"azurkit-{k:03}.json": b"x" for k in range(100)}, ValueError,
                               "/: 100 new entries would outgrow its table's 1 sector(s)")):
        with pytest.raises(error, match="^" + re.escape(why)):
            iso.read(path, None, add=given)


# Step 4.28b: Modkit's unpinned core behaviours (its test census, lane B), ported lean.


def test_a_written_image_is_whole_on_the_disk_before_it_appears_under_its_name(tmp_path, monkeypatch):
    """Modkit's AZ-236: a part file renamed into place with no fsync could
    leave a short file under the final name after a power cut. Cloned or
    streamed, ``pack`` flushes and fsyncs its part at the image's whole
    size before ``out`` exists; each write (5000 B here) is smaller than
    Python's buffer, so a stream that forgot to flush it first would sync
    less."""
    src = tmp_path / "in.iso"
    src.write_bytes(image({"a.bin": fill("a", 90), "gamedata/big.xbr": fill("big", 3 * S)}))
    built = iso.read(src, {"gamedata/big.xbr": fill("B", 3 * S + 1)})
    synced, out, fsync = [], [None], os.fsync

    def recording(fd: int) -> None:
        synced.append((os.fstat(fd).st_size, out[0].exists()))
        fsync(fd)

    monkeypatch.setattr(os, "fsync", recording)
    monkeypatch.setattr(iso, "CHUNK", 5000)   # a whole chunk past the buffer's 8 KiB is written through it
    clone = iso._clone
    for name, made in (("cloned", clone), ("streamed", lambda source, part: None)):
        monkeypatch.setattr(iso, "_clone", made)
        synced.clear()
        out[0] = tmp_path / f"{name}.iso"
        assert iso.pack(built, out[0]) == built.sha256()
        assert (synced[:1], out[0].stat().st_size) == ([(built.size, False)], built.size), name

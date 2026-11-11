"""The leak guard (D961): no game image, xemu disk, EEPROM dump, guest RAM
snapshot or private key in a file this repository tracks, could commit or
pushes; game files and game bytes may be committed."""

from __future__ import annotations

import gzip
import hashlib
import io
import os
import subprocess
import tarfile
import zipfile
import zlib
from pathlib import Path

import pytest

import bootstrap
from azurkit.core import iso
from azurkit.tools.saves import sign
from tests import _leak_guard

ROOT = Path(__file__).resolve().parent.parent


def test_game_files_and_bytes_pass_and_images_disks_eeproms_snapshots_and_keys_are_refused(tmp_path):
    """Synthetic files (a format's magic, no game bytes): an XBE, an XBR
    (also inside a gzip file), a save, an 8-byte vanilla literal and a
    disassembly listing pass. Refused: an XISO first part (the volume
    descriptor at 0x10000), an .iso, .xiso or .iso.NNN name, a qcow2 disk,
    an EEPROM .bin, a private key and a guest RAM snapshot (AZL3SNAP); the
    XISO part and the snapshot also inside a gzip file, each member on its
    own (a later one, after a note or 17 MiB of zeros; the snapshot also in
    one with a bad CRC and in one whose deflate data is damaged after it),
    and an ISO part's name inside one named ``.GZ``."""
    snapshot = b"AZL3SNAP" + bytes(56)
    gz = gzip.compress(snapshot)
    deflate = zlib.compressobj(wbits=31)
    damaged = deflate.compress(snapshot) + deflate.flush(zlib.Z_SYNC_FLUSH) + bytes([7])   # then a reserved block type
    xiso_part = bytes(0x10000) + b"MICROSOFT*XBOX*MEDIA" + bytes(0x7EC)
    refused = {
        "part.000": (xiso_part, "XISO volume descriptor at 0x10000"),
        "part.001.gz": (gzip.compress(xiso_part), "inside its gzip: XISO volume descriptor at 0x10000"),
        "notes.part.gz": (gzip.compress(b"note\n") + gzip.compress(xiso_part),
                          "inside its gzip: XISO volume descriptor at 0x10000"),
        "AZURIK.ISO.007.GZ": (gzip.compress(bytes(64)),
                              "inside its gzip: ISO image or part (.iso/.xiso/.iso.NNN name)"),
        **{name: (bytes(64), "ISO image or part (.iso/.xiso/.iso.NNN name)")
           for name in ("Azurik.ISO", "europe.xiso", "azurik.iso.007")},
        "hdd.qcow2": (b"QFI\xfb" + bytes(60), "qcow2 disk image (an xemu HDD) at 0"),
        "xemu_eeprom.bin": (bytes(256), "EEPROM (eeprom*.bin name)"),
        "deploy": (b"-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n", "private key at 0"),
        "w1.snap": (snapshot, "guest RAM snapshot (console keys) at 0"),
        "w1.snap.gz": (gz, "inside its gzip: guest RAM snapshot (console keys) at 0"),
        **{name: (gzip.compress(first) + gz, "inside its gzip: guest RAM snapshot (console keys) at 0")
           for name, first in (("two.snap.gz", b"note\n"), ("big.snap.gz", bytes(17 << 20)))},
        "crc.snap.gz": (gz[:-8] + bytes([gz[-8] ^ 0xFF]) + gz[-7:],
                        "inside its gzip: guest RAM snapshot (console keys) at 0"),
        "cut.snap.gz": (damaged, "inside its gzip: guest RAM snapshot (console keys) at 0"),
    }
    passed = {
        "default.xbe": b"XBEH" + bytes(60), "config.xbr": b"xobx" + bytes(60),
        "level.xbr.gz": gzip.compress(b"xobx" + bytes(60)),
        "slot.sav": b"fileversion=1\n", "SaveMeta.xbx": b"\xff\xfe" + "Name=Slot\r\n".encode("utf-16-le"),
        "literal.py": b'X = bytes.fromhex("0102030405060708")\n',
        "listing.md": b"".join(f"0001234{i}  50  PUSH EAX\n".encode() for i in range(4)),
    }
    for name, data in {**{n: d for n, (d, _) in refused.items()}, **passed}.items():
        (tmp_path / name).write_bytes(data)
    assert {name: _leak_guard.check(tmp_path, name) for name in refused | passed} == {
        **{name: why for name, (_, why) in refused.items()}, **dict.fromkeys(passed)}


def _tar(*files: tuple[str, bytes]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w") as tar:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


def _zip(method: int, *files: tuple[str, bytes]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", method) as archive:
        for name, data in files:
            archive.writestr(name, data)
    return out.getvalue()


def test_a_tar_or_zip_archive_is_refused_for_a_file_it_holds(tmp_path):
    """Each file a tar (also in a gzip file) or a zip (stored or deflated,
    also in a gzip file or in another archive) holds is checked by its name
    in the archive and its bytes, behind a game file, also in a zip over
    :data:`MAX_TEXT` read with no seek (in a gzip file, or pushed); archives
    of game files pass."""
    xbe, xbr = ("default.xbe", b"XBEH" + bytes(60)), ("config.xbr", b"xobx" + bytes(60))
    key = ("id", b"-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n")
    big = _zip(zipfile.ZIP_STORED, ("pad.xbr", bytes(_leak_guard.MAX_TEXT)), ("xemu/eeprom.bin", bytes(256)))
    refused = {
        "fixtures.tar": (_tar(xbe, ("xemu/eeprom.bin", bytes(256))),
                         "inside its archive: xemu/eeprom.bin: EEPROM (eeprom*.bin name)"),
        "sandbox.tgz": (gzip.compress(_tar(xbe, ("xbox_hdd.qcow2", b"QFI\xfb" + bytes(60)))),
                        "inside its gzip: inside its archive: xbox_hdd.qcow2: qcow2 disk image (an xemu HDD) at 0"),
        "store.zip": (_zip(zipfile.ZIP_DEFLATED, xbr, ("w1.l3snap", b"AZL3SNAP" + bytes(56))),
                      "inside its archive: w1.l3snap: guest RAM snapshot (console keys) at 0"),
        "parts.zip": (_zip(zipfile.ZIP_STORED, ("part.000", bytes(0x10000) + b"MICROSOFT*XBOX*MEDIA")),
                      "inside its archive: part.000: XISO volume descriptor at 0x10000"),
        "keys.zip.gz": (gzip.compress(_zip(zipfile.ZIP_DEFLATED, xbe, key)),
                        "inside its gzip: inside its archive: id: private key at 0"),
        "nested.zip": (_zip(zipfile.ZIP_STORED, ("inner.tar.gz", gzip.compress(_tar(xbe, ("eeprom.bin", bytes(256)))))),
                       "inside its archive: inner.tar.gz: inside its gzip: inside its archive: eeprom.bin: "
                       "EEPROM (eeprom*.bin name)"),
        "big.zip.gz": (gzip.compress(big, 1),
                       "inside its gzip: inside its archive: xemu/eeprom.bin: EEPROM (eeprom*.bin name)"),
    }
    passed = {"game.tar": _tar(xbe, xbr),
              "game.zip": _zip(zipfile.ZIP_DEFLATED, xbe, ("level.xbr.gz", gzip.compress(xbr[1])))}
    for name, data in {**{n: d for n, (d, _) in refused.items()}, **passed}.items():
        (tmp_path / name).write_bytes(data)
    assert {name: _leak_guard.check(tmp_path, name) for name in refused | passed} == {
        **{name: why for name, (_, why) in refused.items()}, **dict.fromkeys(passed)}
    assert _leak_guard._check("big.zip", _leak_guard._Piece(io.BytesIO(big), len(big))) == (   # a pushed blob
        "inside its archive: xemu/eeprom.bin: EEPROM (eeprom*.bin name)")


class _Disc(io.RawIOBase):
    """A whole disc image's stand-in, 1 MiB past ``at``: zeros, but the XISO
    volume descriptor's magic at ``at`` (held as those bytes alone)."""

    def __init__(self, at: int) -> None:
        self.at, self.pos, self.size = at, 0, at + (1 << 20)

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, pos: int, whence: int = 0) -> int:
        self.pos = pos
        return pos

    def readinto(self, b) -> int:
        n = max(0, min(len(b), self.size - self.pos))
        b[:n] = bytes(n)
        lo, hi = max(self.at, self.pos), min(self.at + len(_leak_guard.XISO), self.pos + n)
        if lo < hi:
            b[lo - self.pos:hi - self.pos] = _leak_guard.XISO[lo - self.at:hi - self.at]
        self.pos += n
        return n


def test_a_key_past_a_files_start_and_a_whole_disc_images_descriptor_are_refused(tmp_path):
    """A private key's BEGIN line after a certificate or ``openssl pkcs12
    -nodes``'s attributes is refused where it starts, and a whole disc image
    (any name) by its volume descriptor at 0x10000 past each game partition
    core/iso.py opens; 64 KiB of zeros and a 1 MiB file pass."""
    cert = b"-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n"
    keys = {"server.pem": cert + b"-----BEGIN PRIVATE KEY-----\nMIIE\n",
            "bundle.txt": b"Bag Attributes\n    localKeyID: 01\n-----BEGIN RSA PRIVATE KEY-----\r\nMIIE\r\n"}
    for name, data in keys.items():
        (tmp_path / name).write_bytes(data)
    (tmp_path / "zeros.bin").write_bytes(bytes(0x10000))
    (tmp_path / "big.bin").write_bytes(bytes(1 << 20))
    assert {name: _leak_guard.check(tmp_path, name) for name in (*keys, "zeros.bin", "big.bin")} == {
        "server.pem": f"private key at {len(cert):#x}", "bundle.txt": "private key at 0x22",
        "zeros.bin": None, "big.bin": None}
    assert sorted(_leak_guard.DISCS) == list(_leak_guard.DISCS) == sorted(iso._PARTITIONS[1:])
    assert [_leak_guard._check("game.img", _Disc(base + 0x10000)) for base in _leak_guard.DISCS] == [
        f"XISO volume descriptor at {base + 0x10000:#x}" for base in _leak_guard.DISCS]


def test_bios_and_key_files_are_refused_by_name_and_a_certificate_key_file_by_its_fingerprint(tmp_path, monkeypatch):
    """The files sign.py reads the console's keys from: the MCPX boot ROM
    and flash BIOS pair (xemu's names and the fixtures') and a key file, by
    name; a file of at most 64 bytes holding the certificate key, under any
    name, by sign.py's fingerprint (a stand-in key's here); a game's .bin
    passes."""
    assert _leak_guard.CERT_KEY_SHA256_12 == sign.CERT_KEY_SHA256_12
    key = bytes(range(16))
    monkeypatch.setattr(_leak_guard, "CERT_KEY_SHA256_12", hashlib.sha256(key).hexdigest()[:12])
    why = "Xbox BIOS or key file (keys, bootrom, flashrom, mcpx*, complex*, *bios*.bin name)"
    files = {**dict.fromkeys(("bootrom.bin", "mcpx_1.0.bin", "flashrom.bin", "Complex_4627v1.03.bin", "keys.bin",
                              "xbox_bios.bin"), (bytes(512), why)),
             "blob.dat": (bytes(16) + key, "Xbox certificate key"), "dsstdfx.bin": (bytes(32), None)}
    for name, (data, _) in files.items():
        (tmp_path / name).write_bytes(data)
    assert {name: _leak_guard.check(tmp_path, name) for name in files} == {n: w for n, (_, w) in files.items()}


def test_a_push_fails_on_a_refused_file_a_later_commit_deleted(tmp_path):
    """The pre-push hook's scan reads every file the pushed commits add, so
    one committed and deleted again still fails the push, named with the
    commit that added it; a push of clean commits passes."""
    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    git("init", "-q", "-b", "main")
    (tmp_path / "a.txt").write_text("hello\n")
    git("add", "a.txt")
    git("commit", "-q", "-m", "clean")
    clean = git("rev-parse", "HEAD")
    (tmp_path / "hdd.img").write_bytes(b"QFI\xfb" + bytes(60))
    git("add", "hdd.img")
    git("commit", "-q", "-m", "an xemu disk")
    added = git("rev-parse", "HEAD")
    git("rm", "-q", "hdd.img")
    git("commit", "-q", "-m", "gone again")
    zero = "0" * 40
    assert _leak_guard.scan_push(tmp_path, "origin", f"refs/heads/main {clean} refs/heads/main {zero}\n") == []
    head = git("rev-parse", "HEAD")
    assert _leak_guard.scan_push(tmp_path, "origin", f"refs/heads/main {head} refs/heads/main {zero}\n") == [
        f"hdd.img in {added[:12]}: qcow2 disk image (an xemu HDD) at 0"]


def test_the_checkout_scan_refuses_a_staged_file_its_work_tree_copy_no_longer_holds(tmp_path):
    """What the next commit takes is the index's copy: an image part staged
    and then overwritten, and an .iso staged and then deleted, are refused
    as staged; a clean staged file passes."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "game.bin").write_bytes(bytes(0x10000) + b"MICROSOFT*XBOX*MEDIA")
    (tmp_path / "x.iso").write_bytes(bytes(64))
    (tmp_path / "notes.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "game.bin", "x.iso", "notes.txt"], check=True)
    (tmp_path / "game.bin").write_bytes(b"XBEH" + bytes(60))
    (tmp_path / "x.iso").unlink()
    (tmp_path / "notes.txt").write_text("hello again\n")
    assert _leak_guard.scan(tmp_path) == ["game.bin (staged): XISO volume descriptor at 0x10000",
                                          "x.iso (staged): ISO image or part (.iso/.xiso/.iso.NNN name)"]


def test_bootstrap_writes_the_hook_the_global_hook_hands_a_push_to(tmp_path):
    """The owner's global pre-push hook hands a push on only to a hook holding
    this exact line: bootstrap writes it, executable, in the common git dir,
    and refuses to replace a hook that isn't the leak guard's."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    hook = bootstrap.install_hook(tmp_path)
    assert hook.resolve() == (tmp_path / ".git" / "hooks" / "pre-push").resolve()
    assert "# leak-guard pre-push hook, written by `uv run bootstrap.py`" in hook.read_text(encoding="utf-8")
    assert os.access(hook, os.X_OK)
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="isn't the leak guard's"):
        bootstrap.install_hook(tmp_path)


def test_the_checkout_holds_nothing_the_guard_refuses():
    assert _leak_guard.scan(ROOT) == []

"""The leak guard (D961): no game image, xemu disk, EEPROM dump, guest RAM
snapshot or private key in a file this repository tracks, could commit or
pushes; game files and game bytes may be committed."""

from __future__ import annotations

import gzip
import os
import subprocess
import zlib
from pathlib import Path

import pytest

import bootstrap
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

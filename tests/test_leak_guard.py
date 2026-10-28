"""The leak guard (D3, Q273): nothing taken from the game in a file this
repository tracks, could commit or pushes."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

import bootstrap
from tests import _leak_guard

ROOT = Path(__file__).resolve().parent.parent


def _listing(*instructions: str) -> str:
    return "\n".join(instructions) + "\n"


def test_game_files_images_personal_data_keys_and_listings_are_refused(tmp_path, monkeypatch):
    """Refused: a whole game file under any name (its size and sha256 in a
    manifest), the ISO or its parts, an XBE, an XBR, a save, an xemu disk, an
    EEPROM, a guest RAM snapshot, a private key, and 4 or more consecutive
    x86 instruction lines in any text file (Ghidra's, objdump's, IDA's, a
    comment's or trailing comments' after bytes in code). Snippets, prose and
    code that merely name instructions pass."""
    game_file = bytes(range(64)) * 4
    monkeypatch.setattr(_leak_guard, "_whole_files", lambda: {
        len(game_file): {hashlib.sha256(game_file).hexdigest(): "usa ISO's media/a.bik"}})
    files = {
        "renamed.dat": game_file,
        "part.000": bytes(0x10000) + b"MICROSOFT*XBOX*MEDIA" + bytes(0x7EC),
        "azurik.iso.007": bytes(64), "europe.xiso": bytes(64),
        "default.bin": b"XBEH" + bytes(60), "level.dat": b"xobx" + bytes(60),
        "slot.dat": b"fileversion=1\n", "SaveMeta.dat": b"\xff\xfe" + "Name=Slot\r\n".encode("utf-16-le"),
        "hdd.img": b"QFI\xfb" + bytes(60), "xemu_eeprom.bin": bytes(256), "w1.snap": b"AZL3SNAP" + bytes(56),
        "deploy": b"-----BEGIN OPENSSH PRIVATE KEY-----\nAAAA\n",
        "trailing.c": _listing("    0x01, 0x02,  // mov eax, [esp+4]", "    0x03,  /* push eax */",
                               "    0x04,  ; call sub_12360", "    0x05,  # ret").encode(),
        "ghidra.md": _listing("00012345  8B 45 08   MOV EAX,dword ptr [EBP + 0x8]", "0001234A  50  PUSH EAX",
                              "0001234B  E8 10 00 00 00  CALL FUN_00012360", "00012350  C3  RET").encode(),
        "objdump.txt": _listing("   12345:\t8b 45 08\tmov    0x8(%ebp),%eax", "   12348:\t50\tpush   %eax",
                                "   12349:\te8 10 00 00 00\tcall   12360", "   1234e:\tc3\tret").encode(),
        "ida.py": _listing("    # mov     eax, [esp+4]", "    # test    eax, eax", "    # jz      short loc_1234",
                           "    # fld     dword ptr [eax+10h]").encode(),
    }
    allowed = {
        "notes.md": (" ".join(f"{b:02x}" for b in range(256)) * 4 + "\n").encode(),
        "blob.b64": b"QUJD" * 600 + b"\n",
        "prose.md": _listing("We push the commit", "and call it done,", "then test it again", "for a while.",
                             "and leave.").encode(),
        "code.py": _listing("    ok = (a", "          and 0 < b", "          or 5 > c", "          and d[0])").encode(),
        "three.md": _listing("push ebp", "mov ebp, esp", "sub esp, 0x10", "", "ret").encode(),
        "comments.c": _listing("a += 4;  // add 4 more", "if (a) return;  /* test it */", "b = a; c = b;",
                               "x = 1  # or move it").encode(),
        "picture.png": b"\x89PNG\r\n\x1a\n" + bytes(56),
    }
    for name, data in (files | allowed).items():
        (tmp_path / name).write_bytes(data)
    assert {name: _leak_guard.check(tmp_path, name) for name in files | allowed} == {
        "renamed.dat": "the usa ISO's media/a.bik (same size and sha256)",
        "part.000": "XISO volume descriptor at 0x10000",
        "azurik.iso.007": "ISO image or part (.iso/.xiso/.iso.NNN name)",
        "europe.xiso": "ISO image or part (.iso/.xiso/.iso.NNN name)",
        "default.bin": "XBE magic at 0", "level.dat": "XBR magic at 0",
        "slot.dat": "Xbox save (.sav/.xbx name or save header at 0)",
        "SaveMeta.dat": "Xbox save (.sav/.xbx name or save header at 0)",
        "hdd.img": "qcow2 disk image (an xemu HDD) at 0", "xemu_eeprom.bin": "EEPROM (eeprom*.bin name)",
        "w1.snap": "guest RAM snapshot (console keys) at 0", "deploy": "private key at 0",
        "ghidra.md": "x86 disassembly: 4 or more instruction lines from line 1",
        "objdump.txt": "x86 disassembly: 4 or more instruction lines from line 1",
        "ida.py": "x86 disassembly: 4 or more instruction lines from line 1",
        "trailing.c": "x86 disassembly: 4 or more instruction lines from line 1",
        **dict.fromkeys(allowed)}


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
    (tmp_path / "boot.bin").write_bytes(b"XBEH" + bytes(60))
    git("add", "boot.bin")
    git("commit", "-q", "-m", "an XBE")
    added = git("rev-parse", "HEAD")
    git("rm", "-q", "boot.bin")
    git("commit", "-q", "-m", "gone again")
    zero = "0" * 40
    assert _leak_guard.scan_push(tmp_path, "origin", f"refs/heads/main {clean} refs/heads/main {zero}\n") == []
    head = git("rev-parse", "HEAD")
    assert _leak_guard.scan_push(tmp_path, "origin", f"refs/heads/main {head} refs/heads/main {zero}\n") == [
        f"boot.bin in {added[:12]}: XBE magic at 0"]


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

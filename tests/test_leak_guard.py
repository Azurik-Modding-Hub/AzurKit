"""The leak guard (D3, Q273): nothing taken from the game in a file this
repository tracks, could commit or pushes."""

from __future__ import annotations

import gzip
import hashlib
import os
import re
import struct
import subprocess
from pathlib import Path

import pytest

import bootstrap
from azurkit.core import facts, gate, iso
from azurkit.core.xbr import Document
from tests import _leak_guard

ROOT = Path(__file__).resolve().parent.parent


def _listing(*instructions: str) -> str:
    return "\n".join(instructions) + "\n"


def test_game_files_images_personal_data_keys_and_listings_are_refused(tmp_path, monkeypatch):
    """Refused: a whole game file under any name (its size and sha256 in a
    manifest), the ISO or its parts, an XBE, an XBR, a save, an xemu disk, an
    EEPROM, a guest RAM snapshot, a private key, and 4 or more consecutive
    x86 instruction lines in any text file (Ghidra's, objdump's, IDA's, a
    comment's, one ending in a stdcall's ``ret N``, or trailing comments'
    after bytes in code), each also inside a gzip file. Snippets, prose and
    code that merely name instructions pass."""
    game_file = bytes(range(64)) * 4
    monkeypatch.setattr(_leak_guard, "_whole_files", lambda: {
        len(game_file): {hashlib.sha256(game_file).hexdigest(): "usa ISO's media/a.bik"}})
    files = {
        "renamed.dat": game_file,
        "part.000": bytes(0x10000) + b"MICROSOFT*XBOX*MEDIA" + bytes(0x7EC),
        "azurik.iso.007": bytes(64), "europe.xiso": bytes(64),
        "default.bin": b"XBEH" + bytes(60), "level.dat": b"xobx" + bytes(60),
        "level.json.gz": gzip.compress(b"xobx" + bytes(60)),
        "slot.dat": _leak_guard._SAVE_HEADERS[0] + b"1\n",
        "SaveMeta.dat": b"\xff\xfe" + "Name=Slot\r\n".encode("utf-16-le"),
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
        "stdcall.js": _listing("// mov eax, [esp+4]", "// push eax", "// call sub_12360", "// ret 4").encode(),
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
        "picture.gif": b"GIF89a" + bytes(58),
    }
    for name, data in (files | allowed).items():
        (tmp_path / name).write_bytes(data)
    assert {name: _leak_guard.check(tmp_path, name) for name in files | allowed} == {
        "renamed.dat": "the usa ISO's media/a.bik (same size and sha256)",
        "part.000": "XISO volume descriptor at 0x10000",
        "azurik.iso.007": "ISO image or part (.iso/.xiso/.iso.NNN name)",
        "europe.xiso": "ISO image or part (.iso/.xiso/.iso.NNN name)",
        "default.bin": "XBE magic at 0", "level.dat": "XBR magic at 0",
        "level.json.gz": "inside its gzip: XBR magic at 0",
        "slot.dat": "Xbox save (.sav/.xbx name or save header at 0)",
        "SaveMeta.dat": "Xbox save (.sav/.xbx name or save header at 0)",
        "hdd.img": "qcow2 disk image (an xemu HDD) at 0", "xemu_eeprom.bin": "EEPROM (eeprom*.bin name)",
        "w1.snap": "guest RAM snapshot (console keys) at 0", "deploy": "private key at 0",
        "ghidra.md": "x86 disassembly: 4 or more instruction lines from line 1",
        "objdump.txt": "x86 disassembly: 4 or more instruction lines from line 1",
        "ida.py": "x86 disassembly: 4 or more instruction lines from line 1",
        "trailing.c": "x86 disassembly: 4 or more instruction lines from line 1",
        "stdcall.js": "x86 disassembly: 4 or more instruction lines from line 1",
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


def test_no_source_literal_holds_a_run_of_a_vanilla_file(tmp_path, usa_iso, europe_iso):
    """A byte or hex literal under src/, tests/, scripts/, web/ or assets/
    that holds 8 or more bytes in a row of either release's vanilla
    default.xbe or config.xbr (the same file in both, named once) is named
    by file, line and lengths, never its bytes: in each form, planted here with the 13
    vanilla bytes 4.1c's fps_unlock once held (also as a hex string in a
    gzipped JSON file), and once with 24 bytes of config.xbr's
    armor_properties row headers (each read from the image now). A run of
    one repeated byte, a hash and a file outside those folders pass. The
    checkout holds none, in a literal or a shim object."""
    read = {}
    for label, path in (("USA", usa_iso), ("Europe", europe_iso)):
        with iso.Reader(path) as r:
            read |= {(label, rel): r.read(rel) for rel in _leak_guard.VANILLA_FILES}
    files = _leak_guard.vanilla_named(read)
    assert sorted(files) == ["Europe default.xbe", "USA default.xbe", "gamedata/config.xbr"]
    usa = facts.of(gate.USA)
    run = files["USA default.xbe"][usa.offset(0x059B37, 30):][17:30]
    config = files["gamedata/config.xbr"]
    rows = config[Document(config).tables["armor_properties"].start + 0x14:][:24]
    escaped = "".join(f"\\x{b:02x}" for b in run)
    plants = {
        "src/a.py": f'X = b"{escaped}"\n',
        "tests/b.py": f'X = bytes.fromhex("{run.hex(" ")}")\n',
        "scripts/c.py": f"X = {list(run)}\n",
        "src/d.py": f"X = (bytes.fromhex('{run[:6].hex()}')\n     + bytes([{', '.join(map(str, run[6:]))}, cap]))\n",
        "web/e.js": (f"const a = [{', '.join(f'0x{b:02x}' for b in run)}];\n// {run.hex(' ')}\n"
                     f'const s = "{escaped}";\nconst d = new Uint8Array([{", ".join(map(str, run))}]);\n'),
        "src/ok.py": f'N = b"\\x90" * 32\nH = "{hashlib.sha256(run).hexdigest()}"\n',
        "docs/out.py": f'X = b"{escaped}"\n',
        "tests/f.py": f'X = bytes.fromhex("{rows.hex()}")\n',
        "assets/icon/g.py": f'X = b"{escaped}"\n',
        "src/h.json.gz": f'{{"x": "{run.hex()}"}}\n',
    }
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for rel, text in plants.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(gzip.compress(text.encode()) if rel.endswith(".gz") else text.encode())
    found = _leak_guard.vanilla_runs(tmp_path, files)
    assert found == sorted([f"{at}: a 13 B literal holds 13 B in a row of the {name}"
                            for at in ("src/a.py:1", "tests/b.py:1", "scripts/c.py:1", "src/d.py:1",
                                       "web/e.js:1", "web/e.js:2", "web/e.js:3", "web/e.js:4",
                                       "assets/icon/g.py:1", "src/h.json.gz (gzip):1")
                            for name, data in files.items() if run in data]
                           + ["tests/f.py:1: a 24 B literal holds 24 B in a row of the gamedata/config.xbr"])
    assert not any(form in line for line in found for form in (run.hex(), run.hex(" "), escaped, repr(run),
                                                               rows.hex()))
    assert _leak_guard.vanilla_runs(ROOT, files) == []


def _object(**sections: bytes) -> bytes:
    """A minimal i386 COFF object (``shimkit``'s kind) with these sections
    (``.text`` code, the rest data), no symbols."""
    at, headers, body = 20 + 40 * len(sections), b"", b""
    for name, data in sections.items():
        flags = 0x60000020 if name == ".text" else 0x40000040
        headers += struct.pack("<8sIIIIIIHHI", name.encode(), 0, 0, len(data), at + len(body), 0, 0, 0, 0, flags)
        body += data
    return struct.pack("<HHIIIHH", 0x014C, len(sections), 0, at + len(body), 0, 0, 0) + headers + body + bytes(4)


def test_a_shim_object_holding_a_run_of_a_vanilla_file_is_named(tmp_path, usa_iso, europe_iso):
    """A committed shim object (``.o``) under src/ is read section by
    section and as a whole file: one holding a run of a vanilla file, 32 or
    more bytes in a row in code or anywhere in the file (after its
    sections, say), or 16 in a data section, is named by file, section (or
    file) and lengths, in the tree and in the commit that added it (still
    named once a later commit removes it), never by its bytes. Shorter
    runs, which compiled code and constants share with the game by chance,
    text, and a constant of at most 3 byte values (the identity matrix the
    save warp keeps, which the game holds too) pass (the checkout's own
    objects are read in the source-literal test's scan of it). A text file
    named ``.o`` is read for literals as any text file is: one holding a
    hex run of 16 bytes is named at its line."""
    read = {}
    for label, path in (("USA", usa_iso), ("Europe", europe_iso)):
        with iso.Reader(path) as r:
            read |= {(label, rel): r.read(rel) for rel in _leak_guard.VANILLA_FILES}
    files = _leak_guard.vanilla_named(read)
    usa, usa_facts = files["USA default.xbe"], facts.of(gate.USA)
    code = usa[usa_facts.offset(0x05F620, 96):][:96]
    floats = usa[usa_facts.offset(0x1980A0, 16):][:16]   # 4 of the game's float constants (.rdata)
    identity = struct.pack("<16f", *(float(i % 5 == 0) for i in range(16)))
    text = re.search(rb"[ -~]{48}", usa).group()
    assert identity in usa and (_leak_guard.OBJECT_RUN, _leak_guard.OBJECT_DATA_RUN) == (32, 16)
    plants = {"src/a/held.o": _object(**{".text": code[:64], ".rdata": text + identity}),
              "src/a/floats.o": _object(**{".rdata": floats}),
              "src/a/tail.o": _object(**{".rdata": text}) + code[:64],
              "src/a/hex.o": f'X = bytes.fromhex("{floats.hex()}")\n'.encode(),
              "src/a/short.o": _object(**{".text": code[:31] + bytes([code[31] ^ 0xFF]) + code[32:63],
                                          ".rdata": floats[:15]}),
              "docs/out.o": _object(**{".text": code[:64]})}

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=t", "-c", "user.email=t@t",
                               "-c", "commit.gpgsign=false", *args], capture_output=True, text=True,
                              check=True).stdout.strip()
    git("init", "-q", "-b", "main")
    for rel, data in plants.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(data)
    named = [f"src/a/{part}{{}}: a {size} B {what} holds {len(run)} B in a row of the {name}"
             for part, size, what, run in (("held.o (.text)", 64, "section", code[:64]),
                                           ("held.o (file)", len(plants["src/a/held.o"]), "file", code[:64]),
                                           ("floats.o (.rdata)", 16, "section", floats),
                                           ("tail.o (file)", len(plants["src/a/tail.o"]), "file", code[:64]),
                                           ("hex.o:1", 16, "literal", floats))
             for name, data in files.items() if run in data]
    assert named and _leak_guard.vanilla_runs(tmp_path, files) == sorted(n.format("") for n in named)
    git("add", *plants)
    git("commit", "-q", "-m", "objects")
    added = git("rev-parse", "HEAD")
    git("rm", "-q", "src/a/held.o", "src/a/floats.o", "src/a/tail.o")
    git("commit", "-q", "-m", "gone again")
    found = _leak_guard.vanilla_runs_in_commits(tmp_path, ["HEAD"], files)
    assert sorted(found) == sorted(n.format(f" in {added[:12]}") for n in named)
    assert not any(form in line for line in found
                   for form in (code.hex(), code[:64].hex(" "), repr(code[:64]), floats.hex()))

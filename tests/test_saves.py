"""Saves (``azurkit.tools.saves``): a slot decoded, edited and signed again,
and the slots read from an xemu HDD image.

Everything here is synthetic: the slots are built in the test, the console
key is a random one found by its own fingerprint (AzurKit never holds the
real key), and the HDD image (a qcow2 and a raw disk with a FATX E: drive)
is written in ``tmp_path``, never committed (the leak guard refuses a qcow2
file)."""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import random
import struct
import zipfile

import pytest

from azurkit import cli, sdk
from azurkit.tools import saves
from azurkit.tools.saves import fatx, sign

ID = "0A1B2C3D4E5F"
CRLF16 = "\r\n".encode("utf-16-le")
META = (b"\xff\xfe" + "Name=Hero".encode("utf-16-le") + CRLF16
        + "TitleName=Azurik: Rise of Perathia".encode("utf-16-le") + CRLF16 + b"\x00\x00" + b"\x01\x02")
MAGIC = b"fileversion=1\n1.000000\n1.000000\n3\n5\n0.750000\n" + bytes(40)
LOC = b"fileversion=1\nlevels/water/w1\n\x00\x07\x00"
UNICODE_META = (b"\xff\xfe" + "Name=Savé Gâme".encode("utf-16-le") + CRLF16 + "TitleName=Azurik".encode("utf-16-le")
                + CRLF16)
NO_FINAL_NEWLINE = b"fileversion=1\nlevels/water/w1\n\xcd\xcc\x8c?\x00\x01"   # loc.sav's spawn bytes end it (AZ-339)
HIGH = b"fileversion=1\n\xff\xe9\n"                                            # 8-bit text, latin-1 (H9)


def _files() -> dict[str, bytes]:
    rnd = random.Random(4705)
    return {"SaveMeta.xbx": META, "SaveImage.xbx": rnd.randbytes(64), "magic.sav": MAGIC, "loc.sav": LOC,
            "inv.sav": struct.pack("<If", 7, 12.5) + bytes(24), "shared.sav": struct.pack("<II", 1, 5) + b"ab",
            "signature.sav": bytes(20), "levels/Town.sav": rnd.randbytes(30), "levels/a1.sav": rnd.randbytes(9),
            "levels/X.SAV": b"upper", "levels/SIGNATURE.SAV": b"skipped", "levels/notes.txt": b"not a save",
            "levels/water/w1.sav": struct.pack("<II", 3, 153) + bytes(40)}


def _walked(files: dict[str, bytes]) -> bytes:
    """The bytes the game's signer hashes for :func:`_files`' slot, by hand: a
    folder's .sav files (blind to case) but signature.sav, by byte order
    (``Town`` before ``X`` before ``a1``), then its folders, the empty one
    too; each name with a NUL."""
    def file(path):
        return path.rsplit("/", 1)[-1].encode() + b"\x00" + files[path]
    return b"".join([*(file(p) for p in ("inv.sav", "loc.sav", "magic.sav", "shared.sav")), b"levels\x00",
                     *(file(p) for p in ("levels/Town.sav", "levels/X.SAV", "levels/a1.sav")), b"air\x00",
                     b"water\x00", file("levels/water/w1.sav")])


def _console(seed: int):
    """A random certificate key, its fingerprint, a flash image whose loader
    holds it under a random boot ROM's RC4 key, that boot ROM, a title key and
    an XBE whose certificate holds it."""
    rnd = random.Random(seed)
    cert, title, mcpx = rnd.randbytes(16), rnd.randbytes(16), rnd.randbytes(0x200)
    loader = bytearray(rnd.randbytes(0x6000))
    loader[0x7C:0x8C] = cert
    flash = rnd.randbytes(0x40000 - 0x6200) + sign._rc4(mcpx[0x1A5:0x1B5], bytes(loader)) + mcpx
    xbe = bytearray(0x400)
    xbe[:4] = b"XBEH"
    xbe[0x104:0x108], xbe[0x118:0x11C] = (0x10000).to_bytes(4, "little"), (0x10178).to_bytes(4, "little")
    xbe[0x238:0x248] = title
    return cert, hashlib.sha256(cert).hexdigest()[:12], flash, mcpx, title, bytes(xbe)


def test_a_save_slot_decodes_edits_and_re_signs(tmp_path):
    """Step 4.7e (Modkit's save_format): a slot read from its folder keeps
    every file and folder (an empty one too); each file decodes by kind (a
    .sav under 8 B is a file, a signature.sav not of 20 B no signature) and
    round-trips (a non-ASCII name, a text part ending in loc.sav's binary
    tail with no newline (AZ-339), 8-bit text (H9), all Modkit's edges);
    an edit changes a text save's line (to latin-1 text too) and keeps the rest of its bytes, and a
    set of edits with any bad one makes none and names each; the console key
    is the HMAC of the XBE's title key under the kernel's certificate key,
    found by its fingerprint in the flash image's RC4 loader (a synthetic
    key: the real one is never in the repo), and a wrong BIOS or a key not
    of 16 B is refused;
    the signature is the game's walk; the slot is written as a new folder
    and as the same zip on every call, its entries named only by the slot's
    checked names, and a name a save can't hold is refused (SEC-12)."""
    folder = tmp_path / "in" / ID
    for path, data in _files().items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)
    (folder / "levels" / "air").mkdir()
    slot = saves.Slot.read(folder)
    assert (slot.id, slot.files, slot.folders) == (ID, dict(sorted(_files().items())),
                                                   {"levels", "levels/air", "levels/water"})

    shown = {d["path"]: d for d in saves.decode(slot)}
    json.dumps(list(shown.values()), allow_nan=False)
    assert {p: d["kind"] for p, d in shown.items()} == {
        "SaveMeta.xbx": "meta", "SaveImage.xbx": "image", "magic.sav": "text", "loc.sav": "text", "inv.sav": "binary",
        "shared.sav": "binary", "signature.sav": "signature", "levels/Town.sav": "binary", "levels/a1.sav": "binary",
        "levels/X.SAV": "file", "levels/SIGNATURE.SAV": "file", "levels/notes.txt": "file",
        "levels/water/w1.sav": "binary"}
    assert shown["SaveMeta.xbx"]["fields"] == [["Name", "Hero"], ["TitleName", "Azurik: Rise of Perathia"]]
    assert (shown["magic.sav"]["version"], shown["magic.sav"]["lines"]) == (1, ["1.000000", "1.000000", "3", "5",
                                                                               "0.750000"])
    assert (shown["inv.sav"]["clock"], shown["levels/water/w1.sav"]["records"], "records" in shown["shared.sav"]) == (
        12.5, 153, False)
    for data in (META, MAGIC, LOC, b"0.333333\r\n0.333333\r\n0\r\n", b"fileversion=01\nx\n",
                 b"fileversion=" + b"1" * 5000 + b"\n", UNICODE_META, NO_FINAL_NEWLINE, HIGH):
        parsed = saves.Meta.from_bytes(data) if data[:2] == b"\xff\xfe" else saves.Text.from_bytes(data)
        assert parsed.to_bytes() == data
    assert saves.Text.from_bytes(b"0.333333\r\n0\r\n").version is None
    assert (saves.Meta.from_bytes(UNICODE_META).get("Name"), saves.Text.from_bytes(NO_FINAL_NEWLINE).lines) == (
        "Savé Gâme", ["levels/water/w1", "\xcd\xcc\x8c?"])
    odd = saves.Slot(ID, {"a.sav": b"\x00\x01\x02", "signature.sav": bytes(19), "levels/signature.sav": bytes(21)})
    assert [d["kind"] for d in saves.decode(odd)] == ["file", "binary", "binary"]   # a short file; no 20 B signature
    assert saves.edit(saves.Slot(ID, {"h.sav": HIGH}), [{"file": "h.sav", "line": 0, "value": "café"}])[0].files == {
        "h.sav": b"fileversion=1\ncaf\xe9\n"}

    edited, done = saves.edit(slot, [{"file": "magic.sav", "line": 4, "value": "0.500000"},
                                     {"file": "loc.sav", "line": 0, "value": "levels/fire/f1"}])
    assert done == [{"file": "magic.sav", "line": 4, "old": "0.750000", "new": "0.500000"},
                    {"file": "loc.sav", "line": 0, "old": "levels/water/w1", "new": "levels/fire/f1"}]
    assert edited.files["magic.sav"] == MAGIC.replace(b"0.750000", b"0.500000")
    assert edited.files["loc.sav"] == b"fileversion=1\nlevels/fire/f1\n\x00\x07\x00"
    assert {p: d for p, d in edited.files.items() if p not in ("magic.sav", "loc.sav")} == {
        p: d for p, d in slot.files.items() if p not in ("magic.sav", "loc.sav")}
    bad = [{"file": "nope.sav", "line": 0, "value": "x"}, {"file": "inv.sav", "line": 0, "value": "x"},
           {"file": "magic.sav", "line": 5, "value": "x"}, {"file": "magic.sav", "line": -1, "value": "x"},
           {"file": "magic.sav", "line": 0, "value": "a\nb"}, {"file": "magic.sav", "line": 1, "value": "Ā"},
           {"file": "magic.sav"}]
    with pytest.raises(ValueError) as refused:
        saves.edit(slot, [{"file": "magic.sav", "line": 0, "value": "2.000000"}, *bad])
    for where in ("nope.sav[0]: no such file", "inv.sav[0]: not a text save", "magic.sav[5]: no such line",
                  "magic.sav[-1]: no such line", "magic.sav[0]: 'a\\nb'", "magic.sav[1]: 'Ā'", "an edit is"):
        assert where in str(refused.value)

    assert sign._rc4(b"Key", b"Plaintext").hex() == "bbf316e8d940af0ad3"   # RC4's classic test vector
    cert, fp, flash, mcpx, title, xbe = _console(4705)
    for data, rom in ((flash, mcpx), (cert, None), (b"\x07" * 99 + cert + b"\x00", None)):
        assert saves.cert_key(data, rom, fingerprint=fp) == cert
    with pytest.raises(ValueError, match="MCPX boot ROM"):
        saves.cert_key(flash, None, fingerprint=fp)
    with pytest.raises(ValueError, match="no Xbox kernel certificate key"):
        saves.key(flash, mcpx, xbe)      # not the retail kernel's key
    for wrong, why in ((b"MZ" + xbe[2:], "not an XBE"), (xbe[:0x200], "outside its file")):
        with pytest.raises(ValueError, match=why):
            saves.title_key(wrong)
    key = saves.signature_key(saves.cert_key(flash, mcpx, fingerprint=fp), saves.title_key(xbe))
    assert key == hmac.new(cert, title, hashlib.sha1).digest()[:16]
    for wrong in (key[:15], key + b"\x00"):
        with pytest.raises(ValueError, match=f"a signature key is 16 bytes, not {len(wrong)}"):
            saves.resign(edited, wrong)
    assert not saves.signed(edited, key)
    resigned = saves.resign(edited, key)
    assert resigned.files["signature.sav"] == hmac.new(key, _walked(resigned.files), hashlib.sha1).digest()
    assert saves.signed(resigned, key) and resigned.folders == slot.folders

    out = resigned.write(tmp_path / "out")
    assert saves.Slot.read(out, id=ID) == resigned
    with pytest.raises(FileExistsError):
        resigned.write(folder)
    packed = resigned.zip()
    assert packed == resigned.zip()
    with zipfile.ZipFile(io.BytesIO(packed)) as z:
        assert z.namelist() == [f"{ID}/", f"{ID}/levels/", f"{ID}/levels/air/", f"{ID}/levels/water/",
                                *(f"{ID}/{p}" for p in sorted(resigned.files))]
        assert {i.date_time for i in z.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        assert {p: z.read(f"{ID}/{p}") for p in resigned.files} == resigned.files
    for name in ("../x.sav", "a\\b.sav", "levels/../../x.sav", "/x.sav", "x\x00.sav", "x\n.sav", "con", "NUL.txt",
                 "x.sav.", "x" * 43, ""):
        with pytest.raises(ValueError, match="isn't a save's file or folder name"):
            saves.Slot(ID, {name: b""})
    with pytest.raises(ValueError, match="isn't a save's file or folder name"):
        saves.Slot("../evil", {})
    for files in ({"a.sav": b"", "A.sav": b""}, {"levels": b"", "levels/x.sav": b""}):
        with pytest.raises(ValueError, match="one name twice"):
            saves.Slot(ID, files)


# ---------------------------------------------------------------------------------------------------------------------
# A synthetic xemu HDD: the E: drive's FATX volume, written as a qcow2 or a raw disk

CLUSTER = 0x4000                                    # 32 sectors, as xemu's E: drive
DATA = fatx.E_OFFSET + 0x1000 + 0x132000            # the FAT's 312,501 32-bit entries, rounded up to 4 KiB
DISK = 8 << 30
DELETED = object()
PARENT = object()


class _Fatx:
    """A FATX E: drive holding ``tree`` ({name: bytes, or a dict for a
    folder; PARENT: a folder record linked to its own folder; DELETED: a
    deleted record}). A file over two clusters is chained out of order
    (its first cluster last), so a chain runs forward and jumps back."""

    def __init__(self, tree: dict):
        self.fat = [0xFFFFFFF8]
        self.clusters: dict[int, bytes] = {}
        self.chains: dict[str, list[int]] = {}
        self._folder(tree, "", self._alloc(1))

    def _alloc(self, n: int) -> list[int]:
        first = len(self.fat)
        chain = list(range(first, first + n))
        if n > 2:
            chain = chain[1:] + chain[:1]
        self.fat += [0] * n
        for at, nxt in zip(chain, chain[1:] + [0xFFFFFFFF]):
            self.fat[at] = nxt
        return chain

    def _folder(self, tree: dict, path: str, chain: list[int]) -> None:
        self.chains[path] = chain
        records = bytearray()
        for name, value in tree.items():
            if value is DELETED:
                records += bytes([0xE5, 0]) + b"gone.sav".ljust(42, b"\xff") + bytes(20)
                continue
            if value is PARENT:
                first, size, attributes = chain[0], 0, 0x10
            elif isinstance(value, dict):
                first, size, attributes = self._alloc(1)[0], 0, 0x10
                self._folder(value, f"{path}{name}/", [first])
            else:
                need = -(-len(value) // CLUSTER)
                sub = self._alloc(need) if need else [0]
                first, size, attributes = sub[0], len(value), 0
                self.chains[path + name] = sub
                for n, at in enumerate(sub):
                    self.clusters[at] = value[n * CLUSTER:(n + 1) * CLUSTER].ljust(CLUSTER, b"\x00")
            raw = name.encode("latin-1")
            records += bytes([len(raw), attributes]) + raw.ljust(42, b"\xff") + struct.pack("<II", first, size)
            records += bytes(12)
        self.clusters[chain[0]] = bytes(records).ljust(CLUSTER, b"\xff")

    def chunks(self) -> dict[int, bytes]:
        """{disk byte: bytes}: the superblock, the FAT and the clusters."""
        out = {fatx.E_OFFSET: b"FATX" + struct.pack("<III", 0x1234, 32, 1).ljust(4092, b"\x00"),
               fatx.E_OFFSET + 0x1000: struct.pack(f"<{len(self.fat)}I", *self.fat)}
        return out | {DATA + (at - 1) * CLUSTER: data for at, data in self.clusters.items()}


def _raw(path, chunks: dict[int, bytes]):
    with open(path, "wb") as f:
        f.truncate(DISK)
        for at, data in chunks.items():
            f.seek(at)
            f.write(data)
    return path


def _qcow2(path, chunks: dict[int, bytes], *, compress=None, **header):
    """A version 3 qcow2 of the disk, 64 KiB clusters: the header, the L1
    table, a refcount table (unread), the L2 tables, the clusters. An
    all-zero cluster is written as the zero flag (version 3's) over a stale
    cluster of 0xAA (what an image keeps after a discard); ``compress``'s
    cluster is marked compressed; ``header`` replaces a header field."""
    c = 1 << 16
    clusters: dict[int, bytearray] = {}
    for at, data in chunks.items():
        done = 0
        while done < len(data):
            index, skip = divmod(at + done, c)
            take = min(len(data) - done, c - skip)
            clusters.setdefault(index, bytearray(c))[skip:skip + take] = data[done:done + take]
            done += take
    per = c // 8
    tables = sorted({index // per for index in clusters})
    l1 = [0] * -(-DISK // (c * per))
    l2 = {t: [0] * per for t in tables}
    body, host = [], 3 + len(tables)
    for index in sorted(clusters):
        data, entry = clusters[index], host * c | 1 << 63
        if not any(data) and header.get("version", 3) == 3:
            data, entry = b"\xaa" * c, entry | 1
        if compress is not None and index == compress // c:
            entry |= 1 << 62
        l2[index // per][index % per] = entry
        body.append(bytes(data))
        host += 1
    for n, t in enumerate(tables):
        l1[t] = (3 + n) * c | 1 << 63
    fields = {"version": 3, "backing": 0, "bits": 16, "size": DISK, "crypt": 0, "l1_size": len(l1),
              "incompatible": 0} | header
    head = struct.pack(">4sIQIIQIIQQIIQQQQII", b"QFI\xfb", fields["version"], fields["backing"], 0, fields["bits"],
                       fields["size"], fields["crypt"], fields["l1_size"], c, 2 * c, 1, 0, 0, fields["incompatible"], 0,
                       0, 4, 104)
    with open(path, "wb") as f:
        f.write(head.ljust(c, b"\x00") + struct.pack(f">{len(l1)}Q", *l1).ljust(c, b"\x00") + bytes(c))
        for t in tables:
            f.write(struct.pack(f">{per}Q", *l2[t]))
        f.write(b"".join(body))
    return path


def _slot_tree(seed: int) -> dict:
    rnd = random.Random(seed)
    return {"SaveMeta.xbx": META, "gone": DELETED, "magic.sav": MAGIC, "inv.sav": rnd.randbytes(3 * CLUSTER + 5),
            "signature.sav": rnd.randbytes(20), "empty.sav": b"",
            "levels": {"air": {}, "water": {"w1.sav": rnd.randbytes(100)}, "life.sav": bytes(6 * CLUSTER)}}


def _slot(id: str, tree: dict, rel: str = "") -> tuple[dict, set]:
    files, folders = {}, set()
    for name, value in tree.items():
        if isinstance(value, dict):
            folders.add(rel + name)
            sub = _slot(id, value, f"{rel}{name}/")
            files |= sub[0]
            folders |= sub[1]
        elif value is not DELETED:
            files[rel + name] = value
    return files, folders


def test_the_sdks_saves_open_edit_sign_and_save_a_slot_and_the_cli_does_too(tmp_path, monkeypatch, capsys):
    """Step 4.7e's hub half: ``sdk.saves`` opens a folder (a host's own ``.DS_Store`` and ``._x`` left out) or files or
    an HDD image's slots, edits a line all or none, signs it with the player's BIOS files (a synthetic key, by its own
    fingerprint) and saves a new folder or a zip, each refusal named: no slot open, no flash given, a file too large
    to be one before any scan; nothing of the key in a reply. ``azurkit save`` inspects and edits, and a re-read slot
    is signed for that console."""
    cert, fp, flash, mcpx, _, xbe = _console(5)
    image = tmp_path / "game.iso"
    image.write_bytes(b"not read")
    monkeypatch.setattr(saves, "key", lambda f, m, x: saves.signature_key(saves.cert_key(f, m, fingerprint=fp),
                                                                         saves.title_key(x)))
    reader = type("R", (), {"__init__": lambda s, path: None, "__enter__": lambda s: s, "__exit__": lambda s, *a: None,
                            "read": lambda s, name: xbe})
    monkeypatch.setattr(sdk.iso, "Reader", reader)
    folder = tmp_path / "in" / ID
    for path, data in _files().items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)
    (folder / ".DS_Store").write_bytes(b"host")
    (folder / "levels/._a1.sav").write_bytes(b"host")
    with pytest.raises(ValueError, match="no slot 'nope' is open"):
        sdk.saves({"do": "edit", "id": "nope", "edits": []})
    [opened] = sdk.saves({"do": "open", "folder": str(folder)})["slots"]
    paths = {file["path"] for file in opened["files"]}
    assert opened["id"] == ID and paths == set(_files())
    with pytest.raises(ValueError, match="99"):
        sdk.saves({"do": "edit", "id": ID, "edits": [{"file": "magic.sav", "line": 99, "value": "1"}]})
    edited = sdk.saves({"do": "edit", "id": ID, "edits": [{"file": "magic.sav", "line": 2, "value": "9"}]})
    assert edited["changes"] == [{"file": "magic.sav", "line": 2, "old": "3", "new": "9"}]
    with pytest.raises(ValueError, match="signing needs your flash image"):
        sdk.saves({"do": "sign", "id": ID, "iso": str(image)})
    with pytest.raises(ValueError, match="that is no BIOS file"):
        sdk.saves({"do": "sign", "id": ID, "iso": str(image), "flash": bytes((4 << 20) + 1)})
    signed = sdk.saves({"do": "sign", "id": ID, "iso": str(image), "flash": flash, "mcpx": mcpx})
    assert signed["was"] is False and signed["signed"] is True and cert.hex() not in json.dumps(signed)
    out = tmp_path / "out"
    assert sdk.saves({"do": "save", "id": ID, "out": str(out)})["out"] == str(out)
    again = saves.Slot.read(out, ID)
    assert saves.signed(again, saves.key(flash, mcpx, xbe)) and b"9\n" in again.files["magic.sav"]
    assert sdk.saves({"do": "zip", "id": ID})["data"] == again.zip() and sdk.saves({"do": "zip", "id": ID})["name"] == f"{ID}.zip"
    with pytest.raises(FileExistsError):
        sdk.saves({"do": "save", "id": ID, "out": str(out)})
    assert [v["id"] for v in sdk.saves({"do": "open", "id": "ABC", "files": {"a.sav": b"x"}})["slots"]] == ["ABC"]

    assert cli.main(["save", "inspect", str(out)]) == 0
    assert "magic.sav: text" in capsys.readouterr().out
    flash_file, mcpx_file = tmp_path / "flash.bin", tmp_path / "mcpx.bin"
    flash_file.write_bytes(flash)
    mcpx_file.write_bytes(mcpx)
    done = tmp_path / "done"
    assert cli.main(["save", "edit", str(out), "--set", "magic.sav:2=10", "--flash", str(flash_file), "--mcpx",
                     str(mcpx_file), "--iso", str(image), "--out", str(done)]) == 0
    assert saves.signed(saves.Slot.read(done, ID), saves.key(flash, mcpx, xbe))
    assert cli.main(["save", "edit", str(out)]) == 1


def test_save_speaks_json_and_edits_a_modkit_plan_files_lines_then_each_set_all_or_none(tmp_path, monkeypatch,
                                                                                         capsys):
    """Step 4.24a (Modkit's ``save inspect --json``, ``save edit --plan`` and ``--json``): ``inspect --json`` gives
    the slots as the Tools tab shows them; ``edit`` makes a plan file's edits (Modkit's ``{"edits": [{"file",
    "line_index", "new_value"}]}``, a number or its digits read as Modkit read them), then each ``--set``, signs
    and saves the slot, and ``--json`` gives the folder, each change and whether it was signed before. A plan
    that isn't one, or an edit the slot can't take, is refused by name and nothing is written."""
    _, fp, flash, mcpx, _, xbe = _console(6)
    monkeypatch.setattr(saves, "key", lambda f, m, x: saves.signature_key(saves.cert_key(f, m, fingerprint=fp),
                                                                         saves.title_key(x)))
    reader = type("R", (), {"__init__": lambda s, path: None, "__enter__": lambda s: s, "__exit__": lambda s, *a: None,
                            "read": lambda s, name: xbe})
    monkeypatch.setattr(sdk.iso, "Reader", reader)
    folder, out, plan = tmp_path / ID, tmp_path / "out", tmp_path / "plan.json"
    for path, data in _files().items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(data)
    (tmp_path / "flash.bin").write_bytes(flash)
    (tmp_path / "mcpx.bin").write_bytes(mcpx)
    keys = ["--flash", str(tmp_path / "flash.bin"), "--mcpx", str(tmp_path / "mcpx.bin"), "--iso", str(tmp_path / "x")]
    assert cli.main(["save", "inspect", str(folder), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == sdk.saves({"do": "open", "folder": str(folder)})
    edits = [{"file": "magic.sav", "line_index": 2, "new_value": 7}, {"file": "magic.sav", "line_index": "3",
                                                                      "new_value": "8"}]
    for doc, why in (([], 'not an edit plan, {"edits": [{"file", "line_index", "new_value"}, ...]}'),
                     ({"edits": [edits[0] | {"line_index": 1.5}]},
                      "edit 1 needs file, line_index (a whole number) and new_value"),
                     ({"edits": [edits[0] | {"line_index": 99}]}, None)):
        plan.write_text(json.dumps(doc), encoding="utf-8")
        assert cli.main(["save", "edit", str(folder), "--plan", str(plan), *keys, "--out", str(out)]) == 1
        assert capsys.readouterr().err.startswith(f"azurkit: --plan {plan}: {why}" if why else
                                                  "azurkit: can't make the edits: magic.sav[99]: no such line")
        assert not out.exists()
    plan.write_text(json.dumps({"edits": edits}), encoding="utf-8")
    assert cli.main(["save", "edit", str(folder), "--plan", str(plan), "--set", "magic.sav:3=9", *keys, "--out",
                     str(out), "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"out": str(out), "signed_before": False, "changes": [
        {"file": "magic.sav", "line": 2, "old": "3", "new": "7"}, {"file": "magic.sav", "line": 3, "old": "5", "new": "8"},
        {"file": "magic.sav", "line": 3, "old": "8", "new": "9"}]}
    again = saves.Slot.read(out, ID)
    assert saves.signed(again, saves.key(flash, mcpx, xbe)) and b"\n7\n9\n" in again.files["magic.sav"]


def test_slots_are_read_from_an_xemu_hdd_image(tmp_path):
    """Step 4.7e: Azurik's slots on an xemu HDD (a qcow2, version 3 or 2, and
    a raw disk: the same slots) are the folders under UDATA/4d530007 on its
    FATX E: drive, each read whole (chains out of order, a deleted record
    skipped, an empty file and an empty folder kept, a qcow2 zero cluster
    read as zeros), and nothing else: the title's own files and other
    games' saves are left; a disk with no Azurik save has none. A damaged or
    crafted image is refused by name and never hangs or floods (SEC-12): a
    loop or a short or outward chain, a folder over 4,096 records or linked
    to itself, a name a save can't hold, a qcow2 header field its file can't
    hold, a backing file, an extended L2, a compressed cluster, a cut file,
    no FATX."""
    trees = {ID: _slot_tree(1), "FEDCBA987654": _slot_tree(2)}
    disk = _Fatx({"TDATA": {"4d530007": {"options.sav": b"0\r\n"}},
                  "UDATA": {"4d530004": {"111111111111": {"x.sav": b"another game"}},
                            "4d530007": {"TitleMeta.xbx": META, **trees}}})
    chunks = disk.chunks()
    want = [saves.Slot(id, *_slot(id, tree)) for id, tree in sorted(trees.items())]
    assert saves.slots(_qcow2(tmp_path / "hdd.qcow2", chunks)) == want
    assert saves.slots(_raw(tmp_path / "hdd.img", chunks)) == want
    assert saves.slots(_qcow2(tmp_path / "v2.qcow2", chunks, version=2)) == want
    assert want[0].files["levels/life.sav"] == bytes(6 * CLUSTER) and "levels/air" in want[0].folders
    assert saves.slots(_qcow2(tmp_path / "none.qcow2", _Fatx({"UDATA": {"4d530004": {}}}).chunks())) == []

    inv = disk.chains[f"UDATA/4d530007/{ID}/inv.sav"]

    def fat(links):
        table = list(disk.fat) + [0] * 20
        for at, value in links.items():
            table[at] = value
        return chunks | {fatx.E_OFFSET + 0x1000: struct.pack(f"<{len(table)}I", *table)}

    folder, spare = disk.chains[f"UDATA/4d530007/{ID}/"][0], len(disk.fat)
    long = {folder: spare} | {spare + n: spare + n + 1 for n in range(17)}      # past 16 clusters: 4,096 records

    def crafted(name, value):
        return _Fatx({"UDATA": {"4d530007": {ID: {name: value}}}}).chunks()

    cases = [(fat({inv[1]: inv[0]}), {}, "chain loops"), (fat({inv[2]: 0xFFFFFFFF}), {}, "clusters short"),
             (fat({inv[0]: 0}), {}, "links to cluster 0x0"), (fat({inv[0]: 0x7FFFFFF}), {}, "outside its 1 to"),
             (fat(long), {}, "over 4096 records"),
             (crafted("levels", PARENT), {}, "linked twice"), (crafted("../x.sav", b"x"), {}, "isn't a save's"),
             (crafted("a/b.sav", b"x"), {}, "isn't a save's"), (chunks, {"bits": 40}, "clusters of 2\\*\\*40"),
             (chunks, {"l1_size": 0xFFFFFFF}, "L1 table"), (chunks, {"l1_size": 1}, "L1 table"),
             (chunks, {"backing": 0x200}, "backing file"), (chunks, {"incompatible": 1 << 4}, "extended L2"),
             (chunks, {"version": 4}, "version 4"), (chunks, {"crypt": 1}, "encrypted"),
             (chunks, {"compress": DATA + (inv[0] - 1) * CLUSTER}, "compressed cluster"),
             (chunks | {fatx.E_OFFSET: bytes(16)}, {}, "no FATX volume")]
    for n, (image, header, why) in enumerate(cases):
        with pytest.raises(ValueError, match=why):
            saves.slots(_qcow2(tmp_path / f"crafted{n}.qcow2", image, **header))
    cut = tmp_path / "cut.qcow2"
    cut.write_bytes((tmp_path / "hdd.qcow2").read_bytes()[:5 << 16])
    with pytest.raises(ValueError, match="the image ends"):
        saves.slots(cut)
    (tmp_path / "small.img").write_bytes(bytes(4096))
    with pytest.raises(ValueError, match="too small for the Xbox's E: drive"):
        saves.slots(tmp_path / "small.img")


# Step 4.28b: Modkit's unpinned save command behaviours, ported lean.


def test_save_with_no_verb_exits_2_naming_what_it_needs(capsys):
    """Modkit's M2: ``save`` with no verb dispatched to inspect and died with
    an AttributeError. ``azurkit save`` alone is a usage error, exit 2,
    naming the verb and the slot it needs."""
    with pytest.raises(SystemExit) as exc:
        cli.main(["save"])
    assert exc.value.code == 2
    assert "the following arguments are required: action, FOLDER|FILE.sav|HDD" in capsys.readouterr().err


def test_the_commands_output_replaces_what_the_consoles_code_page_cant_encode(tmp_path):
    """Modkit's AZ-190: on Windows a pipe or a file is written in the ANSI
    code page (cp1252), so a character it has no byte for (a save's text
    line holding 0x81, read as Latin-1; the audio dump's ``→``) failed the
    command with a codec error and exit 1. ``azurkit`` and ``python -m
    devkit`` replace it with ``?`` and go on."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    from tests.test_devkit_media import xbr

    (slot := tmp_path / ID).mkdir()
    (slot / "loc.sav").write_bytes(b"fileversion=1\nlevels/water/w1\x81\n")
    (fx := tmp_path / "fx.xbr").write_bytes(xbr([(b"wave", bytes(range(256)) * 2)], {}))
    for argv, shown in ((["azurkit", "save", "inspect", str(slot)], b"levels/water/w1?"),
                        (["devkit", "audio", "dump", str(fx), "-o", str(tmp_path / "out")], b"  ? ")):
        done = subprocess.run([sys.executable, "-m", *argv], capture_output=True, cwd=Path(__file__).parents[1],
                              env={**os.environ, "PYTHONIOENCODING": "cp1252"}, timeout=120)
        assert (done.returncode, done.stderr) == (0, b""), argv[0]
        assert shown in done.stdout, argv[0]


# --- Step 4.28g: Modkit's save CLI edges (test_save_format, test_save_signature) -------------------------------------


def test_save_reads_a_lone_save_file_signs_a_slot_with_no_edit_and_refuses_bad_input_in_one_line_writing_nothing(
        tmp_path, monkeypatch, capsys):
    """Modkit's ``save`` edges: ``azurkit save inspect`` reads one .sav file as a slot's (a text save's version and
    lines, a signature's digest); ``save edit`` with the BIOS files and no ``--set`` signs the slot as it is (Step 2.84), a folder
    named like a save kept a folder (L25); and each bad input (AZ-141: the output a file or inside the slot it
    reads, the input a file or one save file, a malformed ``--set``, ``--mcpx`` without ``--flash``) is one
    ``azurkit:`` line, exit 1, nothing written."""
    cert, fp, flash, mcpx, _, xbe = _console(7)
    monkeypatch.setattr(saves, "key", lambda f, m, x: saves.signature_key(saves.cert_key(f, m, fingerprint=fp),
                                                                         saves.title_key(x)))
    reader = type("R", (), {"__init__": lambda s, path: None, "__enter__": lambda s: s, "__exit__": lambda s, *a: None,
                            "read": lambda s, name: xbe})
    monkeypatch.setattr(sdk.iso, "Reader", reader)
    slot = tmp_path / ID
    (slot / "old.sav").mkdir(parents=True)
    for name, data in (("magic.sav", MAGIC), ("inv.sav", bytes(16)), ("signature.sav", bytes(20))):
        (slot / name).write_bytes(data)
    for name, data in (("image.iso", b"not read"), ("flash.bin", flash), ("mcpx.bin", mcpx), ("taken.txt", b"x"),
                       ("sample.sav", b"fileversion=1\nhello\nworld\n"), ("signature.sav", bytes(range(20)))):
        (tmp_path / name).write_bytes(data)
    assert cli.main(["save", "inspect", str(tmp_path / "sample.sav")]) == 0
    assert capsys.readouterr().out == "sample.sav: text, 26 B, version 1\n    0 hello\n    1 world\n"
    assert cli.main(["save", "inspect", str(tmp_path / "signature.sav")]) == 0
    assert capsys.readouterr().out == f"signature.sav: signature, 20 B, digest {bytes(range(20)).hex()}\n"

    keys = ["--flash", str(tmp_path / "flash.bin"), "--mcpx", str(tmp_path / "mcpx.bin"), "--iso",
            str(tmp_path / "image.iso")]

    def tree() -> dict:
        return {p.relative_to(tmp_path).as_posix(): p.read_bytes() if p.is_file() else None
                for p in sorted(tmp_path.rglob("*"))}

    before = tree()
    for case, argv in {"output is a file": [slot, *keys, "--out", tmp_path / "taken.txt"],
                       "output inside the input": [slot, *keys, "--out", slot / "out"],
                       "input is a file": [tmp_path / "taken.txt", *keys, "--out", tmp_path / "out"],
                       "input is one save file": [slot / "magic.sav", *keys, "--out", tmp_path / "out"],
                       "malformed --set": [slot, *keys, "--out", tmp_path / "out", "--set", "bogus"],
                       "a --set line that isn't a number": [slot, *keys, "--out", tmp_path / "out", "--set",
                                                            "magic.sav:zzz=9"],
                       "--mcpx without --flash": [slot, *keys[2:], "--out", tmp_path / "out"]}.items():
        assert cli.main(["save", "edit", *map(str, argv)]) == 1, case
        err = capsys.readouterr().err
        assert len(err.splitlines()) == 1 and err.startswith("azurkit: ") and tree() == before, (case, err)

    assert cli.main(["save", "edit", str(slot), *keys, "--out", str(tmp_path / "done")]) == 0
    done = saves.Slot.read(tmp_path / "done", ID)
    assert saves.signed(done, saves.key(flash, mcpx, xbe)) and done.folders == {"old.sav"}
    assert {p: d for p, d in done.files.items() if p != "signature.sav"} == {"inv.sav": bytes(16), "magic.sav": MAGIC}
    assert cert.hex() not in capsys.readouterr().out

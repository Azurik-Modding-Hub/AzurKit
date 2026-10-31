"""A save slot and its files, decoded (Modkit's ``save_format``, ported).

A slot is the folder the game writes under ``UDATA/4d530007/<id>/`` (Azurik's
title id): the Xbox's container files (``SaveMeta.xbx``, a ``Name=`` and
``TitleName=`` list in UTF-16; ``SaveImage.xbx`` and other images), the
game's ``.sav`` files (text: ``loc``, ``magic``, ``options``; binary: ``inv``,
``shared``, the level saves under ``levels/``) and ``signature.sav``, an
HMAC-SHA1 over the rest (``sign.py``). :class:`Slot` holds one in memory,
read from a folder or an HDD image (``fatx.py``), and writes it as a new
folder or a zip; :func:`decode` names what each file holds.

Every name a slot holds is checked once, where the slot is made: one to 42
of FATX's characters, no ``.`` or ``..``, no trailing dot or space, no
device name, so a crafted save can't name a path outside its folder, and the
zip's entries are ``<id>/<path>`` from those names alone (SEC-12). The caps
(:data:`MAX_FILES`, :data:`MAX_BYTES`, :data:`MAX_DEPTH`) are far over a
real slot's (about 45 files, 0.6 MiB, 3 levels) and bound what a folder or
image can make one read."""

from __future__ import annotations

import hashlib
import io
import math
import os
import re
import stat
import struct
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

TITLE = "4d530007"                  # Azurik's title id, its folder under UDATA (and TDATA)
SIGNATURE = "signature.sav"
MAX_FILES = 1024
MAX_BYTES = 32 << 20
MAX_DEPTH = 8
_NAME = re.compile(r"[A-Za-z0-9 !#$%&'()\-.@\[\]^_`{}~]{1,42}")
_DEVICE = re.compile(r"(?i)(?:con|prn|aux|nul|conin\$|conout\$|com[1-9]|lpt[1-9]) *(?:\..*)?")
_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_CRLF16 = b"\r\x00\n\x00"
_BOM = b"\xff\xfe"
_META = ("savemeta.xbx", "titlemeta.xbx")


def _shown(name: str) -> str:
    return repr(name if len(name) <= 48 else name[:48] + "...")


def check_name(name: str) -> str:
    """``name`` when a save may hold it as a file or folder name, else
    ``ValueError`` naming it."""
    if (not isinstance(name, str) or not _NAME.fullmatch(name) or name in (".", "..") or name[-1] in ". "
            or _DEVICE.fullmatch(name)):
        raise ValueError(f"{_shown(name)} isn't a save's file or folder name (1 to 42 of FATX's characters, "
                         "no folder separator, no '.' or '..', no trailing dot or space, no device name)")
    return name


def check_path(path: str) -> str:
    """``path`` (posix, from the slot's folder) when each part is a name a save may hold."""
    parts = path.split("/") if isinstance(path, str) else [path]
    if len(parts) > MAX_DEPTH:
        raise ValueError(f"{_shown(path)} is more than {MAX_DEPTH} folders deep")
    for part in parts:
        check_name(part)
    return path


@dataclass(frozen=True)
class Slot:
    """One save slot: its folder's name, its files (``{path: bytes}``, posix
    from the folder) and every folder under it, empty ones too (the
    signature hashes their names). Made only through its checks: a bad name,
    a file and a folder at one path, two names the same but for case (FATX is
    case-blind) or a cap passed is ``ValueError``."""

    id: str
    files: Mapping[str, bytes]
    folders: frozenset[str] = field(default=frozenset())

    def __post_init__(self):
        check_name(self.id)
        files = {check_path(path): bytes(data) for path, data in self.files.items()}
        if len(files) > MAX_FILES:
            raise ValueError(f"save {self.id!r} holds over {MAX_FILES} files")
        if (size := sum(map(len, files.values()))) > MAX_BYTES:
            raise ValueError(f"save {self.id!r} holds {size} bytes, over {MAX_BYTES}")
        folders = {check_path(path) for path in self.folders}
        for path in [*files, *folders]:
            parts = path.split("/")
            folders.update("/".join(parts[:n]) for n in range(1, len(parts)))
        seen: dict[str, str] = {}
        for path in sorted(files) + sorted(folders):
            if (other := seen.setdefault(path.lower(), path)) != path or (path in files and path in folders):
                raise ValueError(f"save {self.id!r} holds {_shown(other)} and {_shown(path)}: one name twice")
        object.__setattr__(self, "files", dict(sorted(files.items())))
        object.__setattr__(self, "folders", frozenset(folders))

    @classmethod
    def read(cls, folder: str | os.PathLike, id: str | None = None) -> Slot:
        """The slot in ``folder`` (its name the slot's id unless ``id``): its
        files and folders, links and other kinds refused by name, the caps
        checked before a file is read."""
        root = Path(folder)
        if not root.is_dir():
            raise NotADirectoryError(f"{root}: not a folder")
        files: dict[str, bytes] = {}
        folders: set[str] = set()
        total = 0

        def walk(path: Path, rel: str) -> None:
            nonlocal total
            for entry in sorted(os.scandir(path), key=lambda e: e.name):
                sub = check_path(f"{rel}{entry.name}")
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISDIR(mode):
                    folders.add(sub)
                    walk(Path(entry.path), sub + "/")
                elif stat.S_ISREG(mode):
                    total += entry.stat(follow_symlinks=False).st_size
                    if len(files) >= MAX_FILES or total > MAX_BYTES:
                        raise ValueError(f"{root}: over {MAX_FILES} files or {MAX_BYTES} bytes, not a save slot")
                    files[sub] = Path(entry.path).read_bytes()
                else:
                    raise ValueError(f"{root}: {sub!r} is a link or a device, not a save file")

        walk(root, "")
        return cls(id if id is not None else root.name, files, frozenset(folders))

    def write(self, out: str | os.PathLike) -> Path:
        """Writes the slot's files and folders into ``out``, a new or empty
        folder (never into one that holds anything: the slot it was read from
        included, D36); returns it."""
        out = Path(out)
        if out.exists() and (not out.is_dir() or any(out.iterdir())):
            raise FileExistsError(f"{out}: must be a new or empty folder")
        out.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.folders):
            (out / path).mkdir()
        for path, data in self.files.items():
            with open(out / path, "xb") as f:
                f.write(data)
        return out

    def zip(self) -> bytes:
        """The slot as a zip, the same bytes on every host: ``<id>/`` and its
        folders and files under it, by the slot's checked names alone,
        stored (no compressor's version in the bytes), with one fixed date."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as z:
            for path in [""] + sorted(self.folders):
                z.writestr(_info(f"{self.id}/{path}/" if path else f"{self.id}/", 0o40755), b"")
            for path, data in self.files.items():
                z.writestr(_info(f"{self.id}/{path}", 0o100644), data)
        return buffer.getvalue()


def _info(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, _ZIP_TIME)
    info.create_system = 3              # Unix, so a Windows host writes the same bytes
    info.external_attr = mode << 16 | (0x10 if name.endswith("/") else 0)
    return info


@dataclass
class Meta:
    """``SaveMeta.xbx`` or ``TitleMeta.xbx``: ``key=value`` lines in UTF-16-LE
    after a byte-order mark, each line's own ending kept (a title may add a
    NUL), and whatever follows the last line as it is."""

    fields: list[list]                  # [key, value, ending bytes]
    tail: bytes = b""
    bom: bool = True

    @classmethod
    def from_bytes(cls, data: bytes) -> Meta:
        bom = data.startswith(_BOM)
        at, fields = (2 if bom else 0), []
        while (end := data.find(_CRLF16, at)) != -1 and (end - at) % 2 == 0:
            try:
                text = data[at:end].decode("utf-16-le")
            except UnicodeDecodeError:
                break
            if "=" not in text:
                break
            key, _, value = text.partition("=")
            ending = _CRLF16 + (b"\x00\x00" if data[end + 4:end + 6] == b"\x00\x00" else b"")
            fields.append([key, value, ending])
            at = end + len(ending)
        return cls(fields, data[at:], bom)

    def get(self, key: str) -> str | None:
        return next((value for k, value, _ in self.fields if k == key), None)

    def to_bytes(self) -> bytes:
        lines = b"".join(f"{k}={v}".encode("utf-16-le") + end for k, v, end in self.fields)
        return (_BOM if self.bom else b"") + lines + self.tail


def is_text(data: bytes) -> bool:
    """A text save starts ``fileversion=`` (``loc``, ``magic``) or is
    headerless printable lines ending in a newline (``options``)."""
    return data.startswith(b"fileversion=") or (data.endswith(b"\n") and all(
        0x20 <= b < 0x7F or b in b"\t\r\n" for b in data))


@dataclass
class Text:
    """A text save: an optional ``fileversion=N`` line, then its lines (LF,
    or CRLF as ``options.sav``) up to the first NUL, then the rest (its
    padding, or ``loc.sav``'s binary tail) as it is. Lines decode as latin-1,
    so every byte comes back."""

    version: int | None
    lines: list[str]
    tail: bytes = b""
    newline: str = "\n"
    final_newline: bool = True

    @classmethod
    def from_bytes(cls, data: bytes) -> Text:
        if not is_text(data):
            raise ValueError("not a text save")
        cut = data.find(b"\x00")
        text, tail = (data, b"") if cut == -1 else (data[:cut], data[cut:])
        text = text.decode("latin-1")
        newline = "\r\n" if text.split("\n", 1)[0].endswith("\r") else "\n"
        lines = text.split(newline)
        final = lines[-1] == ""
        if final:
            lines.pop()
        version = None
        head = lines[0][12:] if lines and lines[0].startswith("fileversion=") else ""
        if head.isdecimal() and f"{int(head)}" == head:     # else it wouldn't come back as it is: a line
            version = int(lines.pop(0)[12:])
        return cls(version, lines, tail, newline, final)

    def to_bytes(self) -> bytes:
        lines = ([] if self.version is None else [f"fileversion={self.version}"]) + self.lines
        return (self.newline.join(lines) + (self.newline if self.final_newline else "")).encode("latin-1") + self.tail


def decode(path: str, data: bytes) -> dict:
    """What the file at ``path`` in a slot holds, for a host to show (JSON:
    no NaN): its ``kind`` (``meta``, ``image``, ``text``, ``binary``,
    ``signature`` or ``file``), its size and sha256, and by kind its fields,
    its lines, a binary save's version and the u32 after it named by its file
    (``inv.sav``'s is a clock, a level save's its record count, AZ-275), or
    the signature's digest."""
    name = path.rsplit("/", 1)[-1].lower()
    out: dict = {"path": path, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    if name.endswith(".xbx"):
        if name in _META and "/" not in path:
            meta = Meta.from_bytes(data)
            return out | {"kind": "meta", "fields": [[k, v] for k, v, _ in meta.fields], "tail": len(meta.tail)}
        return out | {"kind": "image"}
    if not name.endswith(".sav"):
        return out | {"kind": "file"}
    if name == SIGNATURE and len(data) == 20:
        return out | {"kind": "signature", "digest": data.hex()}
    if is_text(data):
        text = Text.from_bytes(data)
        return out | {"kind": "text", "version": text.version, "lines": list(text.lines), "tail": len(text.tail)}
    if len(data) < 8:
        return out | {"kind": "file"}
    version, word = struct.unpack_from("<II", data)
    out |= {"kind": "binary", "version": version, "body": len(data) - 8}
    if name == "inv.sav":
        clock = struct.unpack_from("<f", data, 4)[0]
        out["clock"] = clock if math.isfinite(clock) else None
    elif name != "shared.sav":          # shared.sav's entries start at +4
        out["records"] = word
    return out

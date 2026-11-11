"""Leak guard: no game image, xemu disk, EEPROM dump, guest RAM snapshot,
BIOS or key file or private key in a file this repository tracks, could
commit or pushes (D961: the content repo's rules, Modkit's D153 and D960).

Stdlib only. ``tests/test_leak_guard.py`` runs it in the pure tier, the
``pre-push`` hook that ``bootstrap.py`` writes runs it on every push, and it
runs directly::

    python3 -I tests/_leak_guard.py                 # exit 1 and one line per file on a hit
    python3 -I tests/_leak_guard.py --pre-push <remote> < <git's ref lines>

The first reads every tracked and untracked, not ignored, file, and the
staged copy of each whose work-tree file differs from it (changed or
removed), which the next commit takes. The hook reads every file the pushed
commits add or change, in the commits no remote-tracking ref of ``<remote>``
reaches (a new remote: the whole history), so a file committed and deleted
again is caught too.

Game files and game bytes may be committed (D961): an XBE, an XBR, a clip, a
texture, a save, a snippet, a byte literal, a disassembly listing. Refused:

- the ISO, whole or in parts: an XISO or its first part
  (``MICROSOFT*XBOX*MEDIA`` at 0x10000, the volume descriptor), a whole disc
  image (the descriptor at 0x10000 past a game partition's start,
  :data:`DISCS`), or an ``.iso``/``.xiso``/``.iso.NNN`` name (the parts that
  rebuild one);
- an xemu HDD image (qcow2, ``QFI\\xfb`` at 0), an EEPROM dump (an ``eeprom``
  name ending ``.bin``; console keys), a guest RAM snapshot (``AZL3SNAP`` at
  0, Modkit's L3 snapshots; console keys) or a private key (a ``-----BEGIN
  … PRIVATE KEY-----`` line in its first :data:`MAGIC_SPAN` bytes);
- the files the console's keys are read from (``tools/saves/sign.py``): the
  MCPX boot ROM and flash BIOS pair or a key file, by an Xbox BIOS or key
  file name (``keys.bin``, ``bootrom.bin``, ``flashrom.bin``, ``mcpx*.bin``,
  ``complex*.bin``, ``*bios*.bin``), and a file of at most 64 bytes holding
  the retail certificate key (:data:`CERT_KEY_SHA256_12`, sign.py's
  fingerprint).

A gzip file (``1f 8b`` at 0) is refused for what it holds as well: each
member on its own (:class:`_Inflated`: read to its end, past a bad CRC or
size and up to a damaged spot), named as the file without its ``.gz``, is
checked by every rule here. So is each file a tar (``ustar`` at 257, also
inside a gzip file) or a zip (``PK\\x03\\x04`` at 0) holds, by its name in
the archive, up to a damaged spot: an encrypted zip member, or one in a
method zipfile can't read, by its name alone; a zip read with no seek (a
pushed or staged one, or one in a gzip file or a tar) is copied first, held
up to :data:`MAX_TEXT` and on disk past it. Other archives (7z, rar, zstd,
xz, bzip2) are checked as files.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parent.parent
MAGIC_SPAN = 0x10020
CHUNK = 1 << 16          # read at a time; a zlib call inflates at most 16 of them
DEPTH = 3                # the most wrappings unwrapped (a tar in a gzip in a zip ...)
MAX_TEXT = 16 << 20      # of a zip read with no seek (a blob, in a gzip file or a tar), the most held in memory
DISCS = (0x2080000, 0xFD90000, 0x18300000)   # a whole disc image's game partition (core/iso.py's)
XISO = b"MICROSOFT*XBOX*MEDIA"
GZIP = b"\x1f\x8b"
_ISO_NAME = re.compile(r"\.x?iso(\.\d+)?$")   # an image or a part of one (azurik.iso.007)
_PRIVATE_KEY = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\r?\n")
_BIOS_NAME = re.compile(r"^(keys|bootrom|flashrom)\.bin$|^(mcpx|complex).*\.bin$|bios.*\.bin$")
CERT_KEY_SHA256_12 = "0961021c45b7"   # sha256[:12] of the retail kernels' certificate key (sign.py's)


def check_blob(rel: str, head: bytes) -> str | None:
    """Why a file ``rel`` whose first :data:`MAGIC_SPAN` bytes are ``head``
    can't be committed, or ``None``."""
    name = rel.lower().rsplit("/", 1)[-1]
    if head[0x10000:0x10000 + len(XISO)] == XISO:
        return "XISO volume descriptor at 0x10000"
    if _ISO_NAME.search(name):
        return "ISO image or part (.iso/.xiso/.iso.NNN name)"
    if head[:4] == b"QFI\xfb":
        return "qcow2 disk image (an xemu HDD) at 0"
    if "eeprom" in name and name.endswith(".bin"):
        return "EEPROM (eeprom*.bin name)"
    if head[:8] == b"AZL3SNAP":
        return "guest RAM snapshot (console keys) at 0"
    if key := _PRIVATE_KEY.search(head):
        return f"private key at {key.start():#x}" if key.start() else "private key at 0"
    if _BIOS_NAME.search(name):
        return "Xbox BIOS or key file (keys, bootrom, flashrom, mcpx*, complex*, *bios*.bin name)"
    if len(head) <= 64 and any(hashlib.sha256(head[at:at + 16]).hexdigest()[:12] == CERT_KEY_SHA256_12
                               for at in range(len(head) - 15)):
        return "Xbox certificate key"
    return None


def _deflate_at(data: bytes) -> int | None:
    """Where the deflate data of the gzip member starting ``data`` begins,
    past its header (RFC 1952: 10 bytes, then FEXTRA, FNAME, FCOMMENT and
    FHCRC as its flags say), or ``None`` when the header is cut short."""
    flags, at = data[3] if len(data) > 3 else 0, 10
    if flags & 0x04:   # FEXTRA: its length, then its bytes
        at += 2 + int.from_bytes(data[at:at + 2], "little")
    for flag in (0x08, 0x10):   # FNAME, FCOMMENT: zero-terminated
        if flags & flag and not (at := data.find(b"\0", at) + 1):
            return None
    at += 2 if flags & 0x02 else 0   # FHCRC
    return at if at <= len(data) else None


class _Reader(Protocol):
    def read(self, n: int, /) -> bytes: ...


def _read(f: _Reader, n: int) -> bytes:
    """``n`` bytes of ``f``, fewer only at its end."""
    out = f.read(n)
    while len(out) < n and (more := f.read(n - len(out))):
        out += more
    return out


class _Chain:
    """``head``, then the rest of ``f``."""

    def __init__(self, head: bytes, f: _Reader) -> None:
        self._head, self._f = head, f

    def read(self, n: int) -> bytes:
        if self._head:
            out, self._head = self._head[:n], self._head[n:]
            return out
        return self._f.read(n)


class _Inflated:
    """One gzip member's inner bytes, read forward from ``src`` (``pending``
    first): raw deflate past its header, so no header or trailer check (CRC
    or size) drops what it holds; a truncated member reads to its end and a
    damaged one to the damaged spot (the zlib call that fails is inflated
    again a byte at a time, as zlib drops the output of a call that raises).
    :meth:`end` reads the rest and gives what follows its deflate data, or
    ``None`` when it was cut short or damaged."""

    def __init__(self, src: _Reader, pending: bytes) -> None:
        self._src, self._in, self._z = src, pending, zlib.decompressobj(-15)
        self._out, self._done, self._rest = bytearray(), False, None

    def _more(self) -> None:
        self._in = self._in or self._src.read(CHUNK)
        if not self._in:   # truncated
            try:
                self._out += self._z.flush()
            except zlib.error:
                pass
            self._done = True
            return
        before = self._z.copy()
        try:
            self._out += self._z.decompress(self._in, CHUNK << 4)
        except zlib.error:   # damaged: what precedes the damage, then no more
            for i in range(len(self._in)):
                try:
                    self._out += before.decompress(self._in[i:i + 1])
                except zlib.error:
                    break
            self._done = True
            return
        self._in = self._z.unconsumed_tail
        if self._z.eof:
            self._done, self._rest = True, self._z.unused_data

    def read(self, n: int) -> bytes:
        while len(self._out) < n and not self._done:
            self._more()
        out = bytes(self._out[:n])
        del self._out[:n]
        return out

    def end(self) -> bytes | None:
        while not self._done:
            self._more()
            self._out.clear()
        return self._rest


def _members(src: _Reader) -> Iterator[_Inflated]:
    """Each member of the gzip file read from ``src``, in order, the next
    once the last is read to its end (a damaged or cut-short member is the
    last); a member's trailer is skipped unchecked."""
    data = b""
    while True:
        while len(data) < len(GZIP) and (more := src.read(CHUNK)):
            data += more
        if not data.startswith(GZIP):
            return
        while (at := _deflate_at(data)) is None and (more := src.read(CHUNK)):
            data += more
        if at is None:
            return
        member = _Inflated(src, data[at:])
        yield member
        if (data := member.end()) is None:
            return
        while len(data) < 8 and (more := src.read(CHUNK)):
            data += more
        data = data[8:]


def _seekable(f: _Reader) -> bool:
    try:
        return bool(f.seekable())
    except AttributeError:   # a gzip member or a file in a tar
        return False


def _disc(f: _Reader) -> str | None:
    """Why ``f``, read :data:`MAGIC_SPAN` bytes in, is a whole disc image,
    or ``None``."""
    seekable, at = _seekable(f), MAGIC_SPAN
    for base in DISCS:
        want = base + 0x10000
        if seekable:
            f.seek(want)
        else:   # read forward to it
            while at < want and (skipped := len(f.read(min(want - at, CHUNK << 4)))):
                at += skipped
        if (got := _read(f, len(XISO))) == XISO:
            return f"XISO volume descriptor at {want:#x}"
        if len(got) < len(XISO):
            return None
        at = want + len(XISO)
    return None


def _tar(src: _Reader, depth: int) -> str | None:
    """Why a file of the tar read from ``src`` can't be committed, or
    ``None``."""
    try:
        with tarfile.open(fileobj=src, mode="r|") as tar:   # forward only
            for member in tar:
                if member.isfile() and (why := _check(member.name, tar.extractfile(member), depth + 1)):
                    return f"inside its archive: {member.name}: {why}"
    except (tarfile.TarError, EOFError, OSError):   # damaged or cut short: its files before that were read
        pass
    return None


def _zip(f: _Reader, head: bytes, depth: int) -> str | None:
    """Why a file of the zip archive ``f`` (``head`` read already) can't be
    committed, or ``None``; a zip ``f`` can't seek in is copied whole first
    (its directory is at its end)."""
    if not _seekable(f):
        with tempfile.SpooledTemporaryFile(MAX_TEXT) as copy:
            copy.write(head)
            while more := f.read(CHUNK << 4):
                copy.write(more)
            return _zip(copy, head, depth)
    try:
        with zipfile.ZipFile(f) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                try:
                    with archive.open(info) as member:
                        why = _check(info.filename, member, depth + 1)
                except (RuntimeError, NotImplementedError, zipfile.BadZipFile, EOFError, zlib.error, OSError):
                    why = check_blob(info.filename, b"")   # encrypted, its method unknown or damaged: by its name
                if why:
                    return f"inside its archive: {info.filename}: {why}"
    except (zipfile.BadZipFile, EOFError, OSError, ValueError):   # damaged or cut short
        pass
    return None


def _check(rel: str, f: _Reader, depth: int = 0) -> str | None:
    """:func:`check_blob` for the file ``rel`` read forward from ``f``, and
    for each member of a gzip file (named ``rel`` without ``.gz``, in any
    case) and each file of a tar or a zip archive, :data:`DEPTH` wrappings
    deep; any other file past its head is a whole disc image or not."""
    head = _read(f, MAGIC_SPAN)
    if why := check_blob(rel, head):
        return why
    if depth < DEPTH and head.startswith(GZIP):
        inner = re.sub(r"\.gz\Z", "", rel, flags=re.I)
        for member in _members(_Chain(head, f)):
            if why := _check(inner, member, depth + 1):
                return f"inside its gzip: {why}"
        return None
    if depth < DEPTH and head[257:262] == b"ustar":
        return _tar(_Chain(head, f), depth)
    if depth < DEPTH and head.startswith(b"PK\x03\x04"):
        return _zip(f, head, depth)
    return _disc(f) if len(head) == MAGIC_SPAN else None


def check_bytes(rel: str, data: bytes) -> str | None:
    """:func:`_check` for a file's bytes (its head at least)."""
    return _check(rel, io.BytesIO(data))


def check(root: Path, rel: str) -> str | None:
    """Why ``root/rel`` can't be committed, or ``None`` (as :func:`_check`
    reads it)."""
    with open(root / rel, "rb") as f:
        return _check(rel, f)


def scan(root: Path = ROOT) -> list[str]:
    """``"<path>: <why>"`` for every tracked or untracked, not ignored,
    regular file under ``root`` that :func:`check` refuses (a link's target
    isn't committed), then ``"<path> (staged): <why>"`` for each staged file
    whose work-tree copy differs from it, or is gone, that it refuses."""
    listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            capture_output=True, check=True, timeout=60).stdout.decode()
    problems = []
    for rel in sorted(set(filter(None, listed.split("\0")))):
        if (root / rel).is_symlink() or not (root / rel).is_file():
            continue
        try:
            why = check(root, rel)
        except FileNotFoundError:   # removed since the listing
            continue
        if why:
            problems.append(f"{rel}: {why}")
    stale, staged = set(filter(None, _git(root, "diff-files", "-z", "--name-only").decode().split("\0"))), []
    for entry in filter(None, _git(root, "ls-files", "-z", "--stage").decode().split("\0")) if stale else ():
        meta, rel = entry.split("\t", 1)
        mode, blob, _ = meta.split()
        if rel in stale and mode in ("100644", "100755"):   # files; not links or submodules
            staged.append((rel, blob))
    for (rel, _), piece in zip(staged, _blobs(root, [blob for _, blob in staged]) if staged else (), strict=True):
        if why := _check(rel, piece):
            problems.append(f"{rel} (staged): {why}")
    return problems


def _git(root: Path, *args: str, stdin: bytes = b"") -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, check=True,
                          timeout=600).stdout


def _added(root: Path, revs: list[str]) -> dict[tuple[str, str], str]:
    """``{(path, blob): the first commit adding it}`` for every regular file
    a commit of ``git rev-list revs`` adds or changes, oldest commit first."""
    commits = _git(root, "rev-list", "--reverse", *revs)
    raw = _git(root, "diff-tree", "--stdin", "-r", "-m", "--root", "--no-renames", "-z", stdin=commits)
    first: dict[tuple[str, str], str] = {}
    commit, fields = "", iter(raw.split(b"\0"))
    for field in fields:
        if field.startswith(b":"):
            _, mode, _, blob, status = field.decode().split()
            path = os.fsdecode(next(fields))
            if status != "D" and mode in ("100644", "100755"):   # files; not links or submodules
                first.setdefault((path, blob), commit)
        elif field:
            commit = field.decode()
    return first


class _Piece:
    """``size`` bytes of ``f``, read forward (a blob, never held whole)."""

    def __init__(self, f: _Reader, size: int) -> None:
        self._f, self._left = f, size

    def read(self, n: int) -> bytes:
        out = self._f.read(min(n, self._left)) if self._left else b""
        self._left -= len(out)
        return out

    def end(self) -> None:
        while self.read(CHUNK << 4):
            pass


def _blobs(root: Path, blobs: list[str]) -> Iterator[_Piece]:
    """Each blob's content, in order, each read to its end before the next."""
    with subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as cat:
        for blob in blobs:
            cat.stdin.write(f"{blob}\n".encode())
            cat.stdin.flush()
            piece = _Piece(cat.stdout, int(cat.stdout.readline().split()[2]))   # "<oid> blob <size>\n<content>\n"
            yield piece
            piece.end()
            cat.stdout.read(1)
        cat.stdin.close()


def scan_push(root: Path, remote: str, updates: str) -> list[str]:
    """``"<path> in <commit>: <why>"`` for every file a commit being pushed
    adds or changes that :func:`_check` refuses, named with the first
    such commit. ``remote`` and ``updates`` are a ``pre-push`` hook's first
    argument and stdin; the commits are those the pushed oids reach and no
    ``refs/remotes/<remote>/`` ref does."""
    tips = [oid for oid in (line.split()[1] for line in updates.splitlines() if line.strip()) if oid.strip("0")]
    if not tips:   # only deletions
        return []
    added = list(_added(root, [*tips, "--not", f"--remotes={remote}"]).items())
    problems = []
    for ((path, _), commit), piece in zip(added, _blobs(root, [blob for (_, blob), _ in added]), strict=True):
        if why := _check(path, piece):
            problems.append(f"{path} in {commit[:12]}: {why}")
    return problems


def main() -> int:
    if sys.argv[1:2] == ["--pre-push"]:
        problems = scan_push(ROOT, sys.argv[2], sys.stdin.read())
    else:
        problems = scan(ROOT)
    for problem in problems:
        print(f"leak guard: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

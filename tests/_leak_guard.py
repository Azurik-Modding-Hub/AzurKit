"""Leak guard: no game image, xemu disk, EEPROM dump, guest RAM snapshot or
private key in a file this repository tracks, could commit or pushes (D961:
the content repo's rules, Modkit's D153 and D960).

Stdlib only. ``tests/test_leak_guard.py`` runs it in the pure tier, the
``pre-push`` hook that ``bootstrap.py`` writes runs it on every push, and it
runs directly::

    python3 -I tests/_leak_guard.py                 # exit 1 and one line per file on a hit
    python3 -I tests/_leak_guard.py --pre-push <remote> < <git's ref lines>

The first reads every tracked and untracked, not ignored, file. The hook reads
every file the pushed commits add or change, in the commits no remote-tracking
ref of ``<remote>`` reaches (a new remote: the whole history), so a file
committed and deleted again is caught too.

Game files and game bytes may be committed (D961): an XBE, an XBR, a clip, a
texture, a save, a snippet, a byte literal, a disassembly listing. Refused:

- the ISO, whole or in parts: an XISO or its first part
  (``MICROSOFT*XBOX*MEDIA`` at 0x10000, the volume descriptor), or an
  ``.iso``/``.xiso``/``.iso.NNN`` name (the parts that rebuild one);
- an xemu HDD image (qcow2, ``QFI\\xfb`` at 0), an EEPROM dump (an ``eeprom``
  name ending ``.bin``; console keys), a guest RAM snapshot (``AZL3SNAP`` at
  0, Modkit's L3 snapshots; console keys) or a private key (a ``-----BEGIN
  … PRIVATE KEY-----`` line at 0).

A gzip file (``1f 8b`` at 0) is refused for what it holds as well: each
member on its own (:class:`_Inflated`: read to its end, past a bad CRC or
size and up to a damaged spot), named as the file without its ``.gz``, is
checked by every rule here.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import zlib
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol

ROOT = Path(__file__).resolve().parent.parent
MAGIC_SPAN = 0x10020
CHUNK = 1 << 16          # read at a time; a zlib call inflates at most 16 of them
DEPTH = 3                # the most wrappings unwrapped (a gzip in a gzip ...)
GZIP = b"\x1f\x8b"
_ISO_NAME = re.compile(r"\.x?iso(\.\d+)?$")   # an image or a part of one (azurik.iso.007)
_PRIVATE_KEY = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\r?\n")


def check_blob(rel: str, head: bytes) -> str | None:
    """Why a file ``rel`` whose first :data:`MAGIC_SPAN` bytes are ``head``
    can't be committed, or ``None``."""
    name = rel.lower().rsplit("/", 1)[-1]
    if head[0x10000:0x10014] == b"MICROSOFT*XBOX*MEDIA":
        return "XISO volume descriptor at 0x10000"
    if _ISO_NAME.search(name):
        return "ISO image or part (.iso/.xiso/.iso.NNN name)"
    if head[:4] == b"QFI\xfb":
        return "qcow2 disk image (an xemu HDD) at 0"
    if "eeprom" in name and name.endswith(".bin"):
        return "EEPROM (eeprom*.bin name)"
    if head[:8] == b"AZL3SNAP":
        return "guest RAM snapshot (console keys) at 0"
    if _PRIVATE_KEY.match(head):
        return "private key at 0"
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


def _check(rel: str, f: _Reader, depth: int = 0) -> str | None:
    """:func:`check_blob` for the file ``rel`` read forward from ``f``, and
    for each member of a gzip file (named ``rel`` without ``.gz``, in any
    case), :data:`DEPTH` wrappings deep."""
    head = _read(f, MAGIC_SPAN)
    if why := check_blob(rel, head):
        return why
    if head.startswith(GZIP) and depth < DEPTH:
        inner = re.sub(r"\.gz\Z", "", rel, flags=re.I)
        for member in _members(_Chain(head, f)):
            if why := _check(inner, member, depth + 1):
                return f"inside its gzip: {why}"
    return None


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
    isn't committed)."""
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


def _blobs(root: Path, blobs: list[str]) -> Iterator[bytes]:
    """Each blob's content, in order."""
    with subprocess.Popen(["git", "-C", str(root), "cat-file", "--batch"], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE) as cat:
        for blob in blobs:
            cat.stdin.write(f"{blob}\n".encode())
            cat.stdin.flush()
            size = int(cat.stdout.readline().split()[2])   # "<oid> blob <size>\n<content>\n"
            yield cat.stdout.read(size + 1)[:size]
        cat.stdin.close()


def scan_push(root: Path, remote: str, updates: str) -> list[str]:
    """``"<path> in <commit>: <why>"`` for every file a commit being pushed
    adds or changes that :func:`check_bytes` refuses, named with the first
    such commit. ``remote`` and ``updates`` are a ``pre-push`` hook's first
    argument and stdin; the commits are those the pushed oids reach and no
    ``refs/remotes/<remote>/`` ref does."""
    tips = [oid for oid in (line.split()[1] for line in updates.splitlines() if line.strip()) if oid.strip("0")]
    if not tips:   # only deletions
        return []
    added = list(_added(root, [*tips, "--not", f"--remotes={remote}"]).items())
    problems = []
    for ((path, _), commit), data in zip(added, _blobs(root, [blob for (_, blob), _ in added]), strict=True):
        if why := check_bytes(path, data):
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

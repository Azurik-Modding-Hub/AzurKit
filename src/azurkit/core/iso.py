"""The game's image, an XISO (XDVDFS): reading it, and packing it with some
of its files replaced.

    read(path)          the image as it is, an :class:`Image`
    read(path, files)   the image with ``files`` ({path: new bytes}) in place of the files of those names
    read(path, files, add=root)   and ``root`` ({name: bytes}) as new files in its root folder
    Image.segments()    the image as :class:`Copy`, :class:`Bytes` and :class:`Zero` pieces, in order
    pack(image, out)    writes the image; returns its sha256
    digest(image)       the image's sha256, read through its segments (for a host's thread: pack's sha256=)
    Reader(path|Image)  its entries, a lookup, and a file's bytes, streamed

The volume descriptor sits at sector 32 of the game partition (at 0 in an
XISO, further in on a whole disc image), ``MICROSOFT*XBOX*MEDIA`` at both of
its ends, and names the root folder's table. A folder's table is a binary
search tree of records in the kernel's order (names compared with ``a-z``
upper-cased): left and right child offsets in dwords, the start sector, the
size, the attributes, the name's length and the name. Nothing here starts a
thread or a process, so the web page's worker runs it as it is.
"""

from __future__ import annotations

import bisect
import hashlib
import io
import itertools
import os
import re
import struct
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from stat import UF_COMPRESSED

from azurkit.core import filelist

SECTOR = 2048
CHUNK = 8 << 20                       # every read of a file's bytes, and every write of an image
MAGIC = b"MICROSOFT*XBOX*MEDIA"
_VD_SECTOR = 32
_PARTITIONS = (0, 0x18300000, 0xFD90000, 0x2080000)   # where the game partition starts: an XISO, then disc images
_RECORD = struct.Struct("<HHIIBB")    # left, right, sector, size, attributes, name length
_DIRECTORY = 0x10
_PAD = 32                             # an image a moved file ends is padded to 64 KiB (32 sectors), as vanilla's is
_FILE = 0x20                          # an added file's attributes (archive), as vanilla's files have
_UPPER = {c: c - 32 for c in range(ord("a"), ord("z") + 1)}
# A name no host may write as a file of its own (AZ-216): empty, "." or "..", a separator or a character Windows
# reserves, a trailing dot or space, or a DOS device name.
_UNSAFE = re.compile(r'^\.{0,2}$|[/\\:*?"<>|\x00-\x1f]|[. ]$'
                     r'|^(?i:con|prn|aux|nul|conin\$|conout\$|(?:com|lpt)[1-9\u00b9\u00b2\u00b3]) *(?:\.|$)')


def key(path: str) -> str:
    """``path`` in the kernel's case-blind order (``a-z`` upper-cased)."""
    return path.strip("/").translate(_UPPER)


def _sectors(size: int) -> int:
    return -(-size // SECTOR)


@dataclass(frozen=True)
class Entry:
    path: str      # posix, from the image's root
    sector: int
    size: int
    is_dir: bool
    record: int    # where its record sits, from the partition's start


class Reader:
    """An open image: a file, or an :class:`Image`. Use it in a ``with``."""

    def __init__(self, source: str | os.PathLike | Image):
        self._f = source.open() if isinstance(source, Image) else open(source, "rb")
        self._index: dict[str, Entry] | None = None
        for base in _PARTITIONS:
            vd = self._read(base + _VD_SECTOR * SECTOR, SECTOR)
            if vd[:20] == MAGIC and vd[0x7EC:0x800] == MAGIC:
                self.base = base
                self._root = struct.unpack_from("<II", vd, 20)   # the root folder's table: its sector and size
                return
        self._f.close()
        raise ValueError(f"{source}: no XDVDFS volume descriptor")

    def __enter__(self) -> Reader:
        return self

    def __exit__(self, *exc) -> None:
        self._f.close()

    def _read(self, at: int, n: int) -> bytes:
        self._f.seek(at)
        return self._f.read(n)

    def entries(self) -> Iterator[Entry]:
        """Every file and folder, parents first. ``ValueError`` names the
        first thing the kernel would trip on: a table cut off by the end of
        the image, a link out of its table or back into it, a record across
        a sector's end, names out of order, a name that is empty, ``.``,
        ``..`` or holds ``/``, or a folder whose table another one has."""
        todo, seen = [("", *self._root)], {self._root[0]}
        while todo:
            prefix, sector, size = todo.pop()
            for entry in self._table(prefix, sector, size):
                yield entry
                if entry.is_dir and entry.size:
                    if entry.sector in seen:
                        raise ValueError(f"{entry.path}: a folder cycle (its table is another folder's)")
                    seen.add(entry.sector)
                    todo.append((entry.path + "/", entry.sector, entry.size))

    def _table(self, prefix: str, sector: int, size: int) -> list[Entry]:
        where = prefix.rstrip("/") or "/"
        table = self._read(self.base + sector * SECTOR, size)
        if len(table) < size:
            raise ValueError(f"{where}: its table runs past the end of the image")
        if not size or table[:2] == b"\xff\xff":       # an empty folder's table is all 0xFF
            return []
        out, todo, seen = [], [(0, None, None)], set()
        while todo:
            at, low, high = todo.pop()
            if at in seen or at + _RECORD.size > size:
                raise ValueError(f"{where}: a link {'back to' if at in seen else 'past the end of its table at'} "
                                 f"record {at}")
            seen.add(at)
            left, right, start, length, attributes, n = _RECORD.unpack_from(table, at)
            if at // SECTOR != (at + _RECORD.size + n - 1) // SECTOR:
                raise ValueError(f"{where}: record {at} crosses a sector's end")
            name = table[at + _RECORD.size:at + _RECORD.size + n].decode("latin-1")
            if name in ("", ".", "..") or "/" in name:
                raise ValueError(f"{where}: an entry named {name!r}")
            k = key(name)
            if (low is not None and k <= low) or (high is not None and k >= high):
                raise ValueError(f"{where}: {name!r} is out of the kernel's name order")
            out.append(Entry(prefix + name, start, length, bool(attributes & _DIRECTORY), sector * SECTOR + at))
            todo += [(link * 4, *bounds) for link, bounds in ((right, (k, high)), (left, (low, k))) if link]
        return out

    def find(self, path: str) -> Entry:
        """The entry at ``path``, case-blind; ``FileNotFoundError`` when there is none."""
        if self._index is None:
            self._index = {key(e.path): e for e in self.entries()}
        try:
            return self._index[key(path)]
        except KeyError:
            raise FileNotFoundError(path) from None

    def chunks(self, entry: Entry) -> Iterator[bytes]:
        """A file's bytes, :data:`CHUNK` at a time."""
        at, left = self.base + entry.sector * SECTOR, entry.size
        while left:
            data = self._read(at, min(CHUNK, left))
            if not data:
                raise ValueError(f"{entry.path}: it runs past the end of the image")
            at, left = at + len(data), left - len(data)
            yield data

    def read(self, path: str | Entry) -> bytes:
        """A whole file's bytes."""
        return b"".join(self.chunks(path if isinstance(path, Entry) else self.find(path)))


@dataclass(frozen=True)
class Copy:
    """A span of the input image, at the same offset in the output."""
    offset: int
    size: int


@dataclass(frozen=True)
class Bytes:
    """Bytes a build writes."""
    data: bytes | memoryview = field(repr=False)

    @property
    def size(self) -> int:
        return len(self.data)


@dataclass(frozen=True)
class Zero:
    """Zeros past the input's end."""
    size: int


@dataclass(frozen=True)
class Image:
    """An image a build makes, unwritten until :func:`pack` writes it: the
    input ``source`` with ``writes`` (``(offset, bytes)``, each laid over
    those before it) applied, zero-filled up to ``size``. It reads
    ``source`` and the writes' buffers when it is read, so neither may
    change before then: ``origin`` is ``source``'s size, modification and
    change times when :func:`read` read it, which :func:`pack` holds it to."""
    source: Path
    writes: tuple[tuple[int, bytes], ...] = field(repr=False)
    size: int
    origin: tuple[int, int, int] | None = field(default=None, compare=False)   # source's size, mtime, ctime as read

    def segments(self) -> list[Copy | Bytes | Zero]:
        """The image as pieces that cover it once, in order, each as large
        as it can be: what the web page joins into a Blob (a :class:`Copy`
        is a slice of the player's file), and what :meth:`open` and
        :func:`pack` read."""
        have = os.path.getsize(self.source)
        ends = (x for at, data in self.writes for x in (at, at + len(data)))
        cuts = sorted({0, self.size, min(have, self.size), *(min(x, self.size) for x in ends)})
        runs: list[list] = []                       # [start, end, the index of the write on top | "copy" | "zero"]
        for a, b in itertools.pairwise(cuts):
            top = next((i for i in reversed(range(len(self.writes)))
                        if self.writes[i][0] <= a and b <= self.writes[i][0] + len(self.writes[i][1])),
                       "copy" if a < have else "zero")
            if runs and runs[-1][2] == top:
                runs[-1][1] = b
            else:
                runs.append([a, b, top])
        out: list[Copy | Bytes | Zero] = []
        for a, b, top in runs:
            if top == "copy":
                out.append(Copy(a, b - a))
            elif top == "zero":
                out.append(Zero(b - a))
            else:
                at, data = self.writes[top]
                out.append(Bytes(memoryview(data)[a - at:b - at]))
        return out

    def open(self) -> io.RawIOBase:
        """The image as a read-only binary file."""
        return _ImageFile(self)

    def sha256(self) -> str:
        with self.open() as f:
            return hashlib.file_digest(f, "sha256").hexdigest()


class _ImageFile(io.RawIOBase):
    """An open :class:`Image`, read through its segments."""

    def __init__(self, image: Image):
        super().__init__()
        self._pieces = image.segments()
        self._starts = list(itertools.accumulate((p.size for p in self._pieces), initial=0))
        self._size, self._pos = image.size, 0
        self._source = open(image.source, "rb")

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = os.SEEK_SET) -> int:
        self._pos = (0, self._pos, self._size)[whence] + offset
        return self._pos

    def tell(self) -> int:
        return self._pos

    def readinto(self, buffer) -> int:
        view = memoryview(buffer).cast("B")
        n = max(0, min(len(view), self._size - self._pos))
        done, i = 0, bisect.bisect_right(self._starts, self._pos) - 1
        while done < n:
            piece, skip = self._pieces[i], self._pos + done - self._starts[i]
            take = min(piece.size - skip, n - done)
            part = view[done:done + take]
            if isinstance(piece, Copy):
                self._source.seek(piece.offset + skip)
                if self._source.readinto(part) != take:
                    raise OSError("the input image got shorter while the build read it")
            elif isinstance(piece, Bytes):
                part[:] = piece.data[skip:skip + take]
            else:
                part[:] = bytes(take)
            done, i = done + take, i + 1
        self._pos += n
        return n

    def close(self) -> None:
        if not self.closed:
            self._source.close()
        super().close()


def read(path: str | os.PathLike, files: Mapping[str, bytes] | None = None,
         add: Mapping[str, bytes] | None = None, md5s: Mapping[str, str] | None = None) -> Image:
    """The image at ``path``, with ``files`` (``{path: new bytes}``, matched
    case-blind) in place of the files of those names, and ``add`` (``{name:
    bytes}``) as new files in its root folder. With neither it is the
    input, byte for byte. Otherwise its layout is kept:

    - a file that still fits its sectors is written in place (the bytes past
      its new end stay as they were); one that outgrows them moves past the
      end of the image, the moved files in path order, and the image is then
      padded to 64 KiB;
    - each changed file's record gets its sector and size, and every other
      byte stays where it was;
    - ``filelist.txt`` (one in ``files``, else the image's) gets the md5 and
      size of each changed file it lists, and of each it lists at a size
      other than the file's own (vanilla Europe's ``index.xbr``,
      ``French.xbr`` and ``German.xbr`` lines); it gets no line for an
      added file;
    - each added file goes past the end, after the moved ones, in name
      order, and the root folder's table is rebuilt in its own sectors with
      them (:func:`_table`), every other entry keeping its sector (Q66,
      V10: an image with ``/azurkit.json`` and ``/azurkit.bin`` so made
      boots); a table that would outgrow its sectors is refused, with
      nothing moved (D35).

    ``ValueError`` names what the kernel would trip on in the image it makes
    (a truncated input, say), and ``FileNotFoundError`` a name the image
    doesn't have, before anything is written (D35). ``md5s`` (``{path:
    md5}``) gives the md5 of a file of ``files`` a caller hashed already
    (``filelist.rewrite``'s)."""
    path = Path(path)
    stat = path.stat()
    have = stat.st_size
    writes: list[tuple[int, bytes]] = []
    with Reader(path) as r:
        files = dict(files or {})
        if files:
            files.update(_listing(r, files, md5s))
        base, end = r.base, _sectors(have - r.base)    # the first sector past the image
        first, records = end, {}                       # a replaced file's record -> its sector and size
        for name in sorted(files, key=key):
            entry, data = r.find(name), files[name]
            if entry.is_dir:
                raise IsADirectoryError(f"{name}: a folder, not a file")
            if entry.record in records:
                raise ValueError(f"{name}: the same file is replaced twice")
            sector = entry.sector
            if len(data) > _sectors(entry.size) * SECTOR:
                sector, end = end, end + max(1, _sectors(len(data)))
            records[entry.record] = (sector, len(data))
            writes += [(base + sector * SECTOR, data), (base + entry.record + 4, struct.pack("<II", sector, len(data)))]
        if add:
            end = _add(r, dict(add), records, writes, end)
    size = max([have, *(at + len(data) for at, data in writes)])
    if end > first:
        size = base + -(-end // _PAD) * _PAD * SECTOR
    image = Image(path, tuple(writes), size, _origin(stat))
    try:
        _check(image)
    except ValueError as exc:
        raise ValueError(f"{path}: not an image the kernel can read: {exc}") from None
    return image


def _add(r: Reader, add: dict[str, bytes], records: Mapping[int, tuple[int, int]],
         writes: list[tuple[int, bytes]], end: int) -> int:
    """:func:`read`'s ``add``: each new file's bytes from sector ``end`` on,
    in name order, and the root folder's table rebuilt in its own sectors
    (:func:`_table`) with them, its other entries keeping their sectors
    (or ``records``' new ones); the table's size in the volume descriptor
    where it grew past a size that isn't whole sectors (vanilla's root,
    208 B in USA and 284 B in Europe). Returns the sector after the last
    new file."""
    root, size = r._root
    old = r._table("", root, size)
    have = {key(e.path) for e in old}
    new = []
    for name in sorted(add, key=key):
        if _UNSAFE.search(name) or len(name.encode("latin-1", "replace")) > 255:
            raise ValueError(f"{name!r}: not a name a root entry can hold")
        if key(name) in have:
            raise FileExistsError(f"{name}: already in the image's root (replace it instead)")
        have.add(key(name))
        writes.append((r.base + end * SECTOR, add[name]))
        new.append((name, end, len(add[name]), _FILE))
        end += max(1, _sectors(len(add[name])))
    table = _table([(e.path, *records.get(e.record, (e.sector, e.size)), _attributes(r, e)) for e in old] + new)
    span = max(1, _sectors(size)) * SECTOR
    if len(table) > span:
        raise ValueError(f"/: {len(new)} new entries would outgrow its table's {span // SECTOR} sector(s); "
                         "nothing is moved (D35)")
    writes.append((r.base + root * SECTOR, table.ljust(span, b"\xff")))
    if size % SECTOR and len(table) != size:
        writes.append((r.base + _VD_SECTOR * SECTOR + 24, struct.pack("<I", len(table))))
    return end


def _attributes(r: Reader, entry: Entry) -> int:
    """The attributes byte of ``entry``'s record."""
    return r._read(r.base + entry.record + 12, 1)[0]


def _table(entries: list[tuple[str, int, int, int]]) -> bytes:
    """``entries`` (``(name, sector, size, attributes)``) as one folder's
    table: a balanced search tree in :func:`key` order, its root record at
    offset 0 (a zero link is no child), the others in preorder, each record
    dword-aligned (0xFF after its name) and inside one sector."""
    entries = sorted(entries, key=lambda e: key(e[0]))
    if len({key(e[0]) for e in entries}) != len(entries):
        raise ValueError("two entries of one folder share a name")
    out = bytearray()

    def lay(lo: int, hi: int) -> int:   # the subtree's root record, in dwords (0: none)
        if lo >= hi:
            return 0
        mid = (lo + hi) // 2
        name, sector, size, attributes = entries[mid]
        raw = name.encode("latin-1")
        at = len(out)
        if at // SECTOR != (at + _RECORD.size - 1 + len(raw)) // SECTOR:
            at = -(-at // SECTOR) * SECTOR
        out.extend(b"\xff" * (at + (_RECORD.size + len(raw) + 3 & ~3) - len(out)))
        left, right = lay(lo, mid), lay(mid + 1, hi)
        _RECORD.pack_into(out, at, left, right, sector, size, attributes, len(raw))
        out[at + _RECORD.size:at + _RECORD.size + len(raw)] = raw
        return at // 4

    lay(0, len(entries))
    return bytes(out)


def _listing(r: Reader, files: Mapping[str, bytes], md5s: Mapping[str, str] | None = None) -> dict[str, bytes]:
    """``{name: bytes}`` of the ``filelist.txt`` the image with ``files``
    gets (:func:`read`); empty when it has none."""
    name = next((p for p in files if key(p) == "FILELIST.TXT"), "filelist.txt")
    try:
        text = files[name] if name in files else r.read(name)
    except FileNotFoundError:
        return {}
    replaced, stale = {key(p) for p in files}, {}
    for row in filelist.rows(text):
        try:
            entry = r.find(row.path)
        except FileNotFoundError:
            continue
        if not entry.is_dir and entry.size != row.size and key(row.path) not in replaced:
            stale[row.path] = r.read(entry)
    return {name: filelist.rewrite(text, stale | dict(files), md5s)}


def _check(image: Image) -> None:
    """``ValueError`` naming the first thing the kernel would trip on in
    ``image``: its tables (:meth:`Reader.entries`), a file past its end, or
    two files that share a sector."""
    with Reader(image) as r:
        end, spans, entries = image.size - r.base, [], list(r.entries())
        for e in entries:
            if e.sector * SECTOR + e.size > end:
                raise ValueError(f"{e.path}: it runs past the end of the image")
            if e.size:
                spans.append((e.sector, e.sector + _sectors(e.size), e.path))
    spans.sort()
    for (_, a_end, a), (b_start, _, b) in itertools.pairwise(spans):
        if b_start < a_end:
            raise ValueError(f"{a} and {b} share a sector")


def _origin(stat: os.stat_result) -> tuple[int, int, int]:
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def pack(image: Image, out: str | os.PathLike, progress: Callable[[int, int], object] | None = None, *,
         sha256: Callable[[], str] | None = None) -> str:
    """Write ``image`` to ``out`` and return its sha256, or ``sha256()``'s
    (the same bytes' hash, which a host started earlier: :func:`digest` on a
    thread of its own), called once the bytes are written. Where the file
    system clones (APFS's clonefile, Linux's FICLONE on btrfs or XFS) ``out``
    is a clone of the input with only the image's writes written over it, in
    order, then hashed through its segments; else the image is streamed,
    hashed as it is written (another volume, say: nothing of the clone is
    left). Either way it is a fresh file's mode and holds none of the
    input's extended attributes (its quarantine flag, say) or BSD flags
    (Finder's Locked, say). ``out`` appears
    only once it is whole and on the disk (a fresh ``.part`` beside it,
    fsynced, then renamed into place; D35), and it may not be the image's
    input (D36), nor written once that input has changed since :func:`read`
    read it (``Image.origin``). ``progress(done, total)`` is called before
    the ``.part`` is made and after each :data:`CHUNK` written or hashed; an
    exception it raises cancels the write, and nothing is left behind."""
    out = Path(out)
    if out.exists() and out.samefile(image.source):
        raise ValueError(f"{out}: it is the build's input, which a build never writes over")
    if (origin := getattr(image, "origin", None)) is not None and _origin(os.stat(image.source)) != origin:
        raise ValueError(f"{image.source}: it changed after the build read it; build again")
    if progress is not None:
        progress(0, image.size)
    part = out.with_name(f"{out.name}.{os.urandom(4).hex()}.part")
    try:
        if (fd := _clone(Path(image.source), part)) is not None:
            with os.fdopen(fd, "r+b") as dst:
                _own(dst.fileno(), part)
                if os.fstat(dst.fileno()).st_size < image.size:
                    os.ftruncate(dst.fileno(), image.size)   # zeros past the input's end, as the segments' Zero
                for at, data in image.writes:   # each over those before it, as the segments lay them
                    view = memoryview(data)
                    while view:
                        n = os.pwrite(dst.fileno(), view, at)
                        view, at = view[n:], at + n
                os.fsync(dst.fileno())
            if sha256 is None:
                sha = digest(image, progress)
            else:
                if progress is not None:
                    progress(image.size, image.size)
                sha = sha256()
        else:
            sha = _stream(image, part, progress, sha256)
        os.replace(part, out)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return sha


def _stream(image: Image, part: Path, progress: Callable[[int, int], object] | None,
            sha256: Callable[[], str] | None) -> str:
    """:func:`pack`'s copy where nothing clones: every byte written to a
    fresh ``part``, hashed as it is written (else ``sha256()``)."""
    digest_ = hashlib.sha256()
    with open(part, "xb") as dst, image.open() as src:
        while data := src.read(CHUNK):
            if sha256 is None:
                digest_.update(data)
            dst.write(data)
            if progress is not None:
                progress(src.tell(), image.size)
        dst.flush()
        os.fsync(dst.fileno())
    return digest_.hexdigest() if sha256 is None else sha256()


def _clone(source: Path, part: Path) -> int | None:
    """``part`` made as a clone of ``source`` (its blocks shared until
    either is written), open for writing, where the file system can:
    APFS's ``clonefile`` on macOS, ``FICLONE`` on Linux, without the
    input's BSD flags but its compression (a ``ditto --hfsCompression``
    input's: without it the clone's blocks read as other bytes); ``None``,
    with nothing made, where it can't (another volume, another file system,
    another platform, a flag that won't clear)."""
    source = Path(os.path.realpath(source))   # a link to the image (the user data folder's) clones its target
    if sys.platform == "darwin":
        import ctypes

        libc = ctypes.CDLL(None, use_errno=True)
        if libc.clonefile(os.fsencode(source), os.fsencode(part), ctypes.c_uint32(0)) != 0:
            return None
        try:
            # and its flags: Finder's Locked (uchg) would refuse the writes, hidden hide the save; but
            # UF_COMPRESSED (decmpfs) stays, the flag that says how its blocks read
            os.chflags(part, os.stat(part).st_flags & UF_COMPRESSED)
            os.chmod(part, 0o600)   # the clone has the input's mode (a read-only image's); _own gives it a fresh file's
            return os.open(part, os.O_RDWR)
        except OSError:   # a flag the clone took that won't clear, say: the streamed copy instead
            part.unlink(missing_ok=True)
            return None
    if sys.platform.startswith("linux"):
        import fcntl

        fd = os.open(part, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o666)
        try:
            with open(source, "rb") as src:
                fcntl.ioctl(fd, 0x40049409, src.fileno())   # FICLONE
            return fd
        except OSError:
            os.close(fd)
            part.unlink(missing_ok=True)
            return None
    return None


def _own(fd: int, part: Path) -> None:
    """The clone ``part`` (open as ``fd``) made a fresh file's: the mode
    ``open(part, "xb")`` gives, and none of the input's extended attributes
    (macOS's clonefile copies them: its quarantine flag, say); one the
    system won't let go of stays (harmless to an image)."""
    mask = os.umask(0)
    os.umask(mask)
    os.fchmod(fd, 0o666 & ~mask)
    if sys.platform != "darwin":
        return
    import ctypes

    libc = ctypes.CDLL(None, use_errno=True)
    libc.flistxattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_int]
    libc.flistxattr.restype = ctypes.c_ssize_t
    libc.fremovexattr.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    size = libc.flistxattr(fd, None, 0, 0)
    if size <= 0:
        return
    names = ctypes.create_string_buffer(size)
    size = libc.flistxattr(fd, names, size, 0)
    for name in names.raw[:max(size, 0)].split(b"\0"):
        if name:
            libc.fremovexattr(fd, name, 0)


def digest(image: Image, progress: Callable[[int, int], object] | None = None) -> str:
    """The sha256 of ``image``'s bytes, as :func:`pack` writes them, read
    through its segments :data:`CHUNK` at a time on the caller's thread;
    ``progress(done, total)`` after each (an exception it raises stops
    it)."""
    h, buffer, done = hashlib.sha256(), bytearray(CHUNK), 0
    view = memoryview(buffer)
    with image.open() as src:
        while n := src.readinto(view):
            h.update(view[:n])
            done += n
            if progress is not None:
                progress(done, image.size)
    return h.hexdigest()

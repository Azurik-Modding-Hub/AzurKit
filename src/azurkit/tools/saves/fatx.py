"""The save slots on an xemu HDD image, read-only (Modkit's
``scripts/extract_save.py``, ported with SEC-12's checks).

xemu's disk is a qcow2 file (or a raw image). Its E: drive, partition 1 at
:data:`E_OFFSET` of :data:`E_SIZE` (the retail layout every xemu disk
keeps), is a FATX volume, and Azurik's slots are the folders under
``UDATA/4d530007``: :func:`slots` reads each whole, as a
:class:`~azurkit.tools.saves.container.Slot`. Nothing here writes the image
(D36: a new slot is saved as a folder or a zip).

- qcow2, versions 2 and 3: a big-endian header; the L1 table maps a disk
  cluster's index to an L2 table, the L2 entry to the cluster in the file
  (bits 9-55; none: zeros; bit 0 in version 3: zeros; bit 62: compressed).
- FATX: the superblock (``FATX``, sectors a cluster, the root's cluster),
  the FAT at 0x1000 (16-bit entries under 65,525 clusters, else 32-bit),
  rounded up to 4 KiB, then the data area, its first cluster 1. A folder is
  64-byte records: the name's length (0 or 0xFF ends the folder, 0xE5 a
  deleted record), the attributes (0x10 a folder), the name (42 bytes), the
  first cluster and the size.

A crafted image can't hang or flood the reader (SEC-12): the header's fields
are checked against the file's size (its reads end inside it), the cluster
size is 512 B to 2 MiB, a chain keeps a visited set and stays inside the
volume's clusters (a loop or a link out is refused by name), a folder holds
at most 4,096 records and is walked once, a file's size is checked against
the caps before it is read and against its chain, an image on a backing
file, an encrypted one and a compressed cluster are refused by name, and
every name passes :func:`~azurkit.tools.saves.container.check_name`.

The file is read in aligned :data:`BLOCK` s, each once while a bounded
cache holds it, so a slot and the tables it needs take a few reads (each
File read on the site is slow in Safari)."""

from __future__ import annotations

import os
import struct

from azurkit.tools.saves.container import MAX_BYTES, MAX_FILES, TITLE, Slot, check_name, check_path

E_OFFSET = 0xABE80000
E_SIZE = 0x1312D6000
BLOCK = 1 << 20
_CACHE = 64                       # blocks kept
_SECTOR = 512
_FAT = 0x1000
_RECORD = 64
_RECORDS = 4096                   # a folder's records, at most
_ALL = 8 * MAX_BYTES              # every slot's bytes together, at most
_QCOW2 = b"QFI\xfb"
_OFFSET = 0x00FFFFFFFFFFFE00      # an L1 or L2 entry's offset bits
_COMPRESSED = 1 << 62
_ZERO = 1
_READABLE = 0b1011                # version 3's incompatible features read as they are: dirty, corrupt, compression type
_FEATURES = {2: "an external data file", 4: "extended L2 entries"}


class _Blocks:
    """The image's file, read in aligned blocks."""

    def __init__(self, f, size: int):
        self._f, self.size, self._cache, self.reads = f, size, {}, 0

    def read(self, at: int, n: int) -> bytes:
        if at < 0 or n < 0 or at + n > self.size:
            raise ValueError(f"the image ends at byte {self.size}, before {at + n}")
        out = bytearray()
        while n:
            block, skip = divmod(at, BLOCK)
            data = self._cache.get(block)
            if data is None:
                if len(self._cache) >= _CACHE:
                    del self._cache[next(iter(self._cache))]
                self._f.seek(block * BLOCK)
                data = self._f.read(want := min(BLOCK, self.size - block * BLOCK))
                self.reads += 1
                if len(data) != want:
                    raise ValueError(f"the image changed while it was read (byte {block * BLOCK + len(data)})")
                self._cache[block] = data
            take = data[skip:skip + n]
            out += take
            at += len(take)
            n -= len(take)
        return bytes(out)


class _Raw:
    def __init__(self, blocks: _Blocks):
        self.read, self.size = blocks.read, blocks.size


class _Qcow2:
    def __init__(self, blocks: _Blocks):
        if blocks.size < 104:
            raise ValueError("a qcow2 image shorter than its header")
        head = blocks.read(0, 104)
        _, version, backing, _, bits, size, crypt, l1_size, l1_at = struct.unpack_from(">4sIQIIQIIQ", head)
        if version not in (2, 3):
            raise ValueError(f"a qcow2 image of version {version}: AzurKit reads versions 2 and 3")
        if backing:
            raise ValueError("a qcow2 image on a backing file: AzurKit reads one that holds its whole disk")
        if not 9 <= bits <= 21:
            raise ValueError(f"a qcow2 image with clusters of 2**{bits} bytes: not 512 B to 2 MiB")
        if crypt:
            raise ValueError("an encrypted qcow2 image")
        if version == 3 and (odd := struct.unpack_from(">Q", head, 72)[0] & ~_READABLE):
            raise ValueError("a qcow2 image with " + ", ".join(
                _FEATURES.get(bit, f"incompatible feature bit {bit}") for bit in range(64) if odd >> bit & 1))
        self.version, self.cluster, self.size = version, 1 << bits, size
        self._entries = self.cluster // 8
        if l1_size < -(-size // (self.cluster * self._entries)) or l1_at + 8 * l1_size > blocks.size:
            raise ValueError(f"a qcow2 image whose L1 table ({l1_size} entries at byte {l1_at}) doesn't map its "
                             f"{size}-byte disk inside its {blocks.size}-byte file")
        self._blocks, self._l1_at, self._l1_size = blocks, l1_at, l1_size

    def _l2(self, index: int) -> int:
        l1, l2 = divmod(index, self._entries)
        if l1 >= self._l1_size:
            return 0
        table = struct.unpack(">Q", self._blocks.read(self._l1_at + 8 * l1, 8))[0] & _OFFSET
        return struct.unpack(">Q", self._blocks.read(table + 8 * l2, 8))[0] if table else 0

    def read(self, at: int, n: int) -> bytes:
        if at < 0 or n < 0 or at + n > self.size:
            raise ValueError(f"the disk ends at byte {self.size}, before {at + n}")
        out = bytearray()
        while n:
            index, skip = divmod(at, self.cluster)
            take = min(n, self.cluster - skip)
            entry = self._l2(index)
            if entry & _COMPRESSED:
                raise ValueError(f"a compressed cluster at disk byte {index * self.cluster:#x}: AzurKit reads "
                                 "uncompressed qcow2 images (qemu-img convert -O qcow2 makes one)")
            host = entry & _OFFSET
            out += bytes(take) if not host or (self.version == 3 and entry & _ZERO) else self._blocks.read(
                host + skip, take)
            at += take
            n -= take
        return bytes(out)


class _Volume:
    """The E: drive's FATX volume."""

    def __init__(self, disk: _Raw | _Qcow2):
        if disk.size < E_OFFSET + E_SIZE:
            raise ValueError(f"a {disk.size}-byte disk: too small for the Xbox's E: drive (to byte "
                             f"{E_OFFSET + E_SIZE})")
        magic, _, per, root = struct.unpack_from("<4sIII", disk.read(E_OFFSET, 16))
        if magic != b"FATX":
            raise ValueError("no FATX volume where the Xbox's E: drive starts: not an xemu HDD image")
        if per not in {1 << k for k in range(12)}:
            raise ValueError(f"a FATX volume of {per} sectors a cluster: not a power of two up to 2048")
        self.disk, self.cluster = disk, per * _SECTOR
        count = E_SIZE // self.cluster
        self.width = 2 if count < 0xFFF5 else 4
        self.fat = E_OFFSET + _FAT
        self.data = self.fat + -(-count * self.width // 4096) * 4096
        self.last = min(count - 1, (E_OFFSET + E_SIZE - self.data) // self.cluster)   # clusters 1 to last
        self._end = (1 << 8 * self.width) - 8
        if not 1 <= root <= self.last:
            raise ValueError(f"a FATX root at cluster {root}, outside its 1 to {self.last}")
        self.root, self._folders = root, set()

    def _chain(self, first: int, need: int | None) -> list[int]:
        """``first``'s clusters in order: ``need`` of them (a file's), or to
        the chain's end (a folder's)."""
        out, seen, at = [], set(), first
        while True:
            if not 1 <= at <= self.last:
                raise ValueError(f"a FATX chain links to cluster {at:#x}, outside its 1 to {self.last:#x}")
            if at in seen:
                raise ValueError(f"a FATX chain loops at cluster {at:#x}")
            seen.add(at)
            out.append(at)
            if len(out) == need:
                return out
            if need is None and len(out) > max(1, _RECORDS * _RECORD // self.cluster):
                raise ValueError(f"a FATX folder of over {_RECORDS} records")
            nxt = int.from_bytes(self.disk.read(self.fat + at * self.width, self.width), "little")
            if nxt >= self._end:
                if need is not None:
                    raise ValueError(f"a FATX chain ends {need - len(out)} clusters short of its file's size")
                return out
            at = nxt

    def _read(self, clusters: list[int], size: int) -> bytes:
        out, i = bytearray(), 0
        while i < len(clusters):
            j = i
            while j + 1 < len(clusters) and clusters[j + 1] == clusters[j] + 1:
                j += 1
            out += self.disk.read(self.data + (clusters[i] - 1) * self.cluster, (j - i + 1) * self.cluster)
            i = j + 1
        return bytes(out[:size])

    def records(self, first: int) -> list[tuple[str, bool, int, int]]:
        """The folder at ``first``: (name, is a folder, first cluster, size)
        per record; a folder read twice (a loop) is refused."""
        if first in self._folders:
            raise ValueError(f"a FATX folder at cluster {first:#x} is linked twice")
        self._folders.add(first)
        chain = self._chain(first, None)
        data = self._read(chain, len(chain) * self.cluster)
        out = []
        for at in range(0, len(data), _RECORD):
            n = data[at]
            if n in (0x00, 0xFF):
                break
            if n == 0xE5:
                continue
            if n > 42:
                raise ValueError(f"a FATX record with a {n}-byte name: over 42")
            start, size = struct.unpack_from("<II", data, at + 44)
            out.append((data[at + 2:at + 2 + n].decode("latin-1"), bool(data[at + 1] & 0x10), start, size))
        return out

    def file(self, first: int, size: int) -> bytes:
        return self._read(self._chain(first, -(-size // self.cluster)), size) if size else b""

    def slot(self, id: str, first: int, spent: list[int]) -> Slot:
        """The slot ``id`` whose folder starts at ``first``, read whole; the
        caps are checked before each file is read (``spent``: the bytes
        every slot read so far holds)."""
        files: dict[str, bytes] = {}
        folders: set[str] = set()
        held = 0

        def walk(at: int, rel: str) -> None:
            nonlocal held
            for name, is_folder, start, size in self.records(at):
                path = check_path(rel + check_name(name))
                if is_folder:
                    folders.add(path)
                    if len(folders) > MAX_FILES:
                        raise ValueError(f"save {id!r} holds over {MAX_FILES} folders")
                    walk(start, path + "/")
                    continue
                held += size
                spent[0] += size
                if len(files) >= MAX_FILES or held > MAX_BYTES or spent[0] > _ALL:
                    raise ValueError(f"save {id!r} holds over {MAX_FILES} files or {MAX_BYTES} bytes (or the "
                                     f"disk's saves over {_ALL})")
                files[path] = self.file(start, size)

        walk(first, "")
        return Slot(id, files, frozenset(folders))

    def find(self, *names: str) -> int | None:
        """The cluster of the folder at ``names`` (matched blind to case) from the root, or None."""
        at = self.root
        for want in names:
            at = next((first for name, folder, first, _ in self.records(at) if folder and name.lower() == want.lower()),
                      None)
            if at is None:
                return None
        return at


def slots(path: str | os.PathLike) -> list[Slot]:
    """Azurik's save slots on the xemu HDD image at ``path`` (qcow2 or raw),
    each read whole, by id; none when the disk holds no Azurik save.
    ``ValueError`` names what a damaged or crafted image breaks."""
    with open(path, "rb") as f:
        blocks = _Blocks(f, os.fstat(f.fileno()).st_size)
        disk = _Qcow2(blocks) if blocks.size >= 4 and blocks.read(0, 4) == _QCOW2 else _Raw(blocks)
        volume = _Volume(disk)
        title = volume.find("UDATA", TITLE)
        if title is None:
            return []
        out, spent = [], [0]
        for name, folder, first, _ in volume.records(title):
            if folder:                  # the title's own TitleMeta.xbx and TitleImage.xbx are files beside them
                out.append(volume.slot(check_name(name), first, spent))
        return sorted(out, key=lambda s: s.id)

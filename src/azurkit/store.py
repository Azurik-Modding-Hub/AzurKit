"""What AzurKit keeps between calls and launches, by kind (D1015): one
store of caches, each entry checked whole at every read, the least recently
used removed first past one budget across all the kinds.

A kind (:data:`KINDS`) keeps data only, in its own form: JSON (a value
:func:`encode` writes canonically and :func:`json.loads` reads back) or
AZKP1 (bytes that begin with :data:`AZKP1`, the dress's answers), so
reading an entry of either runs no code: the store never unpickles. One
kind, ``swap``, keeps bytes it doesn't type: a dress's ``AZKP1`` plan and
size (``tools.characters._kept``, no pickle) and the match and pictures
``app.engine._kept`` pickles today, until those move to ``memos`` and
``pictures`` (JSON), the plans to ``dresses`` with them (the page's Storage
lists ``swap``); then it goes. Until then the app's seal (an HMAC under the
install's own key) is what keeps a pickle it didn't write out (SEC-4).

An entry is one file, ``<folder>/<kind>/<key>.kept``: :data:`MAGIC`, the
body's length, its seal and the body, written whole or not at all (a part
file renamed into place). The seal covers the kind, the key, the length and
the body under the host's check (:func:`sha256` by default, the site's; the
app's an HMAC, so an entry another install wrote fails it too). An entry
whose length isn't its file's (a torn tail), whose seal isn't the check's
(altered, or moved to another key or kind) or whose body isn't its kind's
form is a miss, never decoded, and the answer is worked out again: a store
is a convenience.

The budget (:data:`BUDGET`, or any size a host gives) counts every kind's
entries together; each write past it removes the least recently used (read
or written) first, whatever their kind, with the part files killed writes
left and an older AzurKit's pickled swap answers. It removes only files of
those names in the kinds' own folders, never anything else there and never
outside them: what a player keeps (their settings, content installs and the
install's key) is user data in other folders, never evicted (Storage lists
it and Clear removes it by name, the host's).

The store starts no thread, so the page's worker can run it as it is; the
app writes behind the answer (``app.swapcache.Kept``)."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from collections.abc import Callable, Collection, Iterator
from pathlib import Path

MAGIC = b"AZKS1\0"   # an entry's first bytes
AZKP1 = b"AZKP1\0"   # an AZKP1 answer's first bytes (the dress's codec: its JSON head, then its files' zstd patches)
BUDGET = 5 << 30     # the bytes every kind's entries take together, by default (D1015's ~5 GB)
STALE = 3600         # seconds after which a part file is a killed write's, removed by the next write
SUFFIX = ".kept"
LENGTH = struct.Struct("<Q")
SEAL = 32
HEAD = len(MAGIC) + LENGTH.size + SEAL
HEX = frozenset("0123456789abcdef")
FORMS = ("json", "azkp1", "bytes")
KINDS: dict[str, tuple[str, str]] = {   # a kind -> (its form, what Storage says it holds)
    "plans": ("json", "The seeds planned"),
    "layers": ("azkp1", "The layers built"),
    "dresses": ("azkp1", "The characters' dressed bodies"),
    "pictures": ("json", "The characters' pictures"),
    "memos": ("json", "The engine's small answers: a tracker's view, a restore, a tab's"),
    "swap": ("bytes", "The characters' dressed bodies, pictures and G4 matches"),
}

Seal = Callable[[bytes, bytes, bool], "bytes | None"]
"""A host's check: ``seal(head, body, make)``, the :data:`SEAL` bytes an
entry's ``head`` (its kind, key and length) and ``body`` seal to, or
``None`` when it can't seal (the app without its key; ``make``: a write's,
which may make one)."""


def sha256(head: bytes, body: bytes, make: bool = False) -> bytes:
    """The plain check (the site's: a torn or altered entry): the sha256 of
    ``head`` then ``body``."""
    h = hashlib.sha256(head)
    h.update(body)
    return h.digest()


def form(kind: str) -> str:
    """``kind``'s form (:data:`FORMS`), or a refusal by name."""
    if kind not in KINDS:
        raise ValueError(f"store: no kind {kind!r} (the kinds: {', '.join(KINDS)})")
    return KINDS[kind][0]


def _head(kind: str, key: str, length: int) -> bytes:
    return MAGIC + kind.encode() + b"\0" + key.encode() + b"\0" + LENGTH.pack(length)


def _hex(text: str) -> bool:
    return bool(text) and set(text) <= HEX


def ours(name: str) -> str | None:
    """What a file named ``name`` in a kind's folder is, of the store's own
    names: ``"entry"``, ``"part"`` (a write's, renamed into place when
    whole) or ``"pickle"`` (an older AzurKit's swap answer, never read);
    ``None`` for anything else, which the store never touches."""
    stem, _, rest = name.partition(".")
    if not _hex(stem):
        return None
    if rest == SUFFIX[1:]:
        return "entry"
    if rest == "pickle":
        return "pickle"
    return "part" if rest.startswith(("kept.", "pickle.")) and rest.endswith(".part") else None


def encode(kind: str, value: object) -> bytes:
    """``value`` as ``kind`` keeps it (its form's bytes), or a refusal by
    name: a JSON kind's value JSON can't hold (a NaN, an object), ``None``
    (a miss reads as ``None``), bytes an AZKP1 kind's form isn't."""
    shape = form(kind)
    if value is None:
        raise ValueError(f"store: {kind} keeps no None (a miss reads as None)")
    if shape == "json":
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"store: {kind} keeps JSON, which can't hold a {type(value).__name__} ({exc})") from None
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"store: {kind} keeps bytes, not a {type(value).__name__}")
    value = bytes(value)
    if shape == "azkp1" and not value.startswith(AZKP1):
        raise ValueError(f"store: {kind} keeps AZKP1 answers, and these {len(value)} bytes aren't one")
    return value


def decode(kind: str, body: bytes) -> object | None:
    """What ``body`` (:func:`encode`'s) holds, or ``None`` when it isn't
    ``kind``'s form."""
    shape = form(kind)
    if shape == "json":
        try:
            return json.loads(body)
        except ValueError:
            return None
    return None if shape == "azkp1" and not body.startswith(AZKP1) else body


def part(path: Path) -> Path:
    """A part file for ``path``, this write's own."""
    return path.with_name(f"{path.name}.{os.getpid()}.{secrets.token_hex(6)}.part")


def whole(path: Path, *data: bytes) -> None:
    """``data`` at ``path``, whole: a part file of its own, renamed into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    at = part(path)
    try:
        with at.open("wb") as f:
            for chunk in data:
                f.write(chunk)
        at.replace(path)
    finally:
        at.unlink(missing_ok=True)


class Store:
    """The kinds' entries under ``folder``, sealed by ``seal`` (:func:`sha256`
    by default), the least recently used removed past ``budget`` bytes of
    every kind's together."""

    def __init__(self, folder: Path, budget: int = BUDGET, seal: Seal = sha256):
        self.folder, self.budget, self.seal = Path(folder), budget, seal

    def file(self, kind: str, key: str) -> Path:
        """The entry's file, or a refusal by name: a kind there is none of, a
        key that isn't a lowercase hex digest (the engine's keys are)."""
        form(kind)
        if not (isinstance(key, str) and _hex(key)):
            raise ValueError(f"store: a key is a lowercase hex digest, not {key!r}")
        return self.folder / kind / f"{key}{SUFFIX}"

    def get(self, kind: str, key: str) -> object | None:
        """What ``kind`` keeps under ``key`` (used now), or ``None``: none, or
        a torn, altered or foreign entry, never decoded."""
        file = self.file(kind, key)
        try:
            with file.open("rb") as f:
                head, size = f.read(HEAD), os.fstat(f.fileno()).st_size
                if len(head) < HEAD or not head.startswith(MAGIC):
                    return None
                (length,) = LENGTH.unpack_from(head, len(MAGIC))
                if size != HEAD + length:
                    return None   # a torn tail
                body = f.read()
        except OSError:
            return None
        if (len(body) != length or (seal := self.seal(_head(kind, key, length), body, False)) is None
                or not hmac.compare_digest(seal, head[-SEAL:])):
            return None
        if (value := decode(kind, body)) is not None:
            with contextlib.suppress(OSError):
                os.utime(file)   # used now: the newest kept
        return value

    def put(self, kind: str, key: str, value: object) -> bool:
        """Keep ``value`` under ``key`` (:meth:`write`), or a refusal by name
        that writes nothing (:func:`encode`)."""
        return self.write(kind, key, encode(kind, value))

    def write(self, kind: str, key: str, body: bytes) -> bool:
        """Keep ``body`` (:func:`encode`'s) under ``key``, whole or not at
        all, then :meth:`prune`; whether it was kept (not without a seal, nor
        where the folder can't be written)."""
        file = self.file(kind, key)
        if (seal := self.seal(_head(kind, key, len(body)), body, True)) is None:
            return False
        try:
            whole(file, MAGIC, LENGTH.pack(len(body)), seal, body)
        except OSError:
            return False
        self.prune()
        return True

    def _files(self, kinds: Collection[str] | None = None) -> Iterator[tuple[str, str, os.DirEntry]]:
        """Each kind's files of the store's names: ``(kind, what, entry)``."""
        for kind in KINDS if kinds is None else kinds:
            try:
                with os.scandir(self.folder / kind) as found:
                    files = list(found)
            except OSError:
                continue
            for at in files:
                with contextlib.suppress(OSError):
                    if (what := ours(at.name)) and not at.is_dir(follow_symlinks=False):
                        yield kind, what, at

    def prune(self) -> None:
        """Remove the least recently used entries past :attr:`budget` bytes in
        all, whatever their kind, and the part files older than
        :data:`STALE` and the pickles an older AzurKit left."""
        now, entries = time.time(), []
        for _, what, at in self._files():
            with contextlib.suppress(OSError):
                stat = at.stat(follow_symlinks=False)
                if what == "entry":
                    entries.append((stat.st_mtime_ns, stat.st_size, at.path))
                elif what == "pickle" or now - stat.st_mtime > STALE:
                    os.unlink(at.path)
        total = 0
        for _, size, path in sorted(entries, reverse=True):
            total += size
            if total > self.budget:
                with contextlib.suppress(OSError):
                    os.unlink(path)

    def usage(self) -> dict[str, dict[str, int]]:
        """Each kind's ``{"entries", "size"}``: its entries and the bytes its
        files of the store's names take (Storage's)."""
        used = {kind: {"entries": 0, "size": 0} for kind in KINDS}
        for kind, what, at in self._files():
            with contextlib.suppress(OSError):
                used[kind]["size"] += at.stat(follow_symlinks=False).st_size
                used[kind]["entries"] += what == "entry"
        return used

    def clear(self, kinds: Collection[str] | None = None) -> list[str]:
        """Remove ``kinds``' files of the store's names (every kind's by
        default; a kind there is none of is refused first, by name); the
        kinds that held one."""
        for kind in kinds or ():
            form(kind)
        cleared = []
        for kind, _, at in self._files(kinds):
            with contextlib.suppress(OSError):
                os.unlink(at.path)
                cleared += [kind] if kind not in cleared else []
        return cleared

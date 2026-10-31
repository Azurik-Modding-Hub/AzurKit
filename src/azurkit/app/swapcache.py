"""What the app keeps across launches in platformdirs' user cache folder
(Step 4.3i), so a second launch does again none of what a first one worked
out: the images the gate vouched for (``core.gate.STAMPS``: one JSON file,
``stamps.json``, its newest :data:`STAMPS_KEPT` entries, so a picked image
that hasn't changed isn't hashed again) and the swap's answers
(``tools.characters.CACHE``: a folder, ``swap/``, one file an answer, the
newest used kept to :data:`MOST` bytes in all, so a body dressed once
dresses from it). Each is written whole or not at all (a part file renamed
into place); a store that can't be read or written is a store that holds
nothing, as remembering is a convenience. The keys are the engine's: they
name the image's path, size and times, and the swap's code, recipe,
release and earlier layers."""

from __future__ import annotations

import contextlib
import json
import os
import threading
from pathlib import Path

MOST = 2 << 30          # the swap's answers kept, in bytes (each a dressed body's plan: about 110 MB)
STAMPS_KEPT = 64        # the images vouched for, newest kept


def root() -> Path:
    """The user cache folder's AzurKit folder."""
    from platformdirs import user_cache_path
    return user_cache_path("AzurKit", appauthor=False)


def _write(path: Path, data: bytes) -> None:
    """``data`` at ``path``, whole: a part file of this process's, renamed into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.part")
    try:
        part.write_bytes(data)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)


class Folder:
    """``tools.characters.CACHE``: one file an answer under ``folder``, the
    newest used (read or written) kept to ``most`` bytes in all."""

    def __init__(self, folder: Path, most: int = MOST):
        self.folder, self.most = Path(folder), most

    def _file(self, key: str) -> Path:
        if not (key.isascii() and key.isalnum()):   # the engine's keys are sha256 hex digests
            raise ValueError(f"swap cache: a key is a hex digest, not {key!r}")
        return self.folder / f"{key}.pickle"

    def get(self, key: str) -> bytes | None:
        file = self._file(key)
        try:
            data = file.read_bytes()
            os.utime(file)   # used now: the newest kept
        except OSError:
            return None
        return data

    def put(self, key: str, data: bytes) -> None:
        with contextlib.suppress(OSError):
            _write(self._file(key), data)
            self._prune()

    def _prune(self) -> None:
        """Remove the least recently used answers past :attr:`most` bytes."""
        kept = []
        for file in self.folder.glob("*.pickle"):
            with contextlib.suppress(OSError):
                at = file.stat()
                kept.append((at.st_mtime_ns, at.st_size, file))
        total = 0
        for _, size, file in sorted(kept, key=lambda k: k[0], reverse=True):
            total += size
            if total > self.most:
                file.unlink(missing_ok=True)


class Stamps:
    """``core.gate.STAMPS``: ``{key: the release's name}`` in one JSON file,
    its newest :data:`STAMPS_KEPT` entries (this process's and another's: the
    server's and the engine's both read and add to it)."""

    def __init__(self, file: Path):
        self.file, self.lock = Path(file), threading.Lock()

    def _read(self) -> dict[str, str]:
        try:
            kept = json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in kept.items() if isinstance(v, str)} if isinstance(kept, dict) else {}

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def put(self, key: str, name: str) -> None:
        with self.lock, contextlib.suppress(OSError):
            kept = self._read()
            kept.pop(key, None)
            kept[key] = name   # the newest last
            kept = dict(list(kept.items())[-STAMPS_KEPT:])
            _write(self.file, (json.dumps(kept) + "\n").encode())


def install(folder: Path | None = None) -> None:
    """Keep this process's stamps and swap answers in ``folder`` (the user
    cache folder's AzurKit folder): the app's server and its engine process."""
    from azurkit.core import gate
    from azurkit.tools import characters

    folder = Path(folder) if folder else root()
    gate.STAMPS = Stamps(folder / "stamps.json")
    characters.CACHE = Folder(folder / "swap")

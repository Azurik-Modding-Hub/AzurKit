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
release and earlier layers.

The engine unpickles the swap's answers, so the stores trust only what this
install wrote (SEC-4): each file carries an HMAC-SHA256 under the install's
own key (:func:`key_file`, made once with :mod:`secrets`, in the user data
folder and never the cache folder a shared "speed-up" zip unpacks into).
A file whose MAC isn't this key's (planted, or copied from another
install's cache), or any file once the key is gone, is a miss: nothing of
it is read past its MAC, and the answer is worked out again. The stamps
are signed too: the gate takes a stamp for its check of the image its key
names (the path, size, modification and change times), and where a zip that
ships an image can set those (on Windows st_ctime is the creation time,
which an unzipper restores), a forged ``stamps.json`` would vouch for an
image the gate never read."""

from __future__ import annotations

import contextlib
import hmac
import json
import os
import secrets
import threading
from pathlib import Path

MOST = 2 << 30          # the swap's answers kept, in bytes (each a dressed body's plan: about 110 MB)
STAMPS_KEPT = 64        # the images vouched for, newest kept
KEY = 32                # the install's key, in bytes
MAC = 32                # an HMAC-SHA256, at the head of each swap answer's file


def root() -> Path:
    """The user cache folder's AzurKit folder."""
    from platformdirs import user_cache_path
    return user_cache_path("AzurKit", appauthor=False)


def key_file() -> Path:
    """This install's key: ``cache.key`` in the user data folder."""
    from platformdirs import user_data_path
    return user_data_path("AzurKit", appauthor=False) / "cache.key"


def _part(path: Path) -> Path:
    return path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.part")


def _write(path: Path, *data: bytes) -> None:
    """``data`` at ``path``, whole: a part file of this process's, renamed into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    part = _part(path)
    try:
        with part.open("wb") as f:
            for chunk in data:
                f.write(chunk)
        part.replace(path)
    finally:
        part.unlink(missing_ok=True)


def _secret(file: Path, make: bool) -> bytes | None:
    """The :data:`KEY`-byte key in ``file``; where there is none and
    ``make``, a new one from :mod:`secrets`, written whole (a part file of
    mode 0600, linked into place, so never over the one another process
    made first); ``None`` when there is none or it can't be read or made."""
    try:
        secret = file.read_bytes()
    except FileNotFoundError:
        if not make:
            return None
        part = _part(file)
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            part.unlink(missing_ok=True)
            with open(os.open(part, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
                f.write(secrets.token_bytes(KEY))
            os.link(part, file)
        except FileExistsError:
            pass   # another process's, made first: the install's key
        except OSError:
            return None
        finally:
            part.unlink(missing_ok=True)
        return _secret(file, make=False)
    except OSError:
        return None
    return secret if len(secret) == KEY else None


class _Signer:
    """HMAC-SHA256s under the install's key in ``file``, read once."""

    def __init__(self, file: Path | None):
        self.file, self.secret = Path(file) if file else key_file(), None

    def mac(self, *head: bytes, make: bool) -> hmac.HMAC | None:
        """An HMAC under the key, fed ``head`` (each ended by a NUL), or
        ``None`` without a key (``make``: one is made where there is none)."""
        if self.secret is None:
            self.secret = _secret(self.file, make)
        if self.secret is None:
            return None
        return hmac.new(self.secret, b"".join(h + b"\0" for h in head), "sha256")


class Folder:
    """``tools.characters.CACHE``: one file an answer under ``folder`` (its
    MAC under the key in ``key``, :func:`key_file`'s by default, then its
    bytes), the newest used (read or written) kept to ``most`` bytes in all."""

    def __init__(self, folder: Path, most: int = MOST, key: Path | None = None):
        self.folder, self.most, self.signer = Path(folder), most, _Signer(key)

    def _file(self, key: str) -> Path:
        if not (key.isascii() and key.isalnum()):   # the engine's keys are sha256 hex digests
            raise ValueError(f"swap cache: a key is a hex digest, not {key!r}")
        return self.folder / f"{key}.pickle"

    def get(self, key: str) -> bytes | None:
        file = self._file(key)
        if (mac := self.signer.mac(b"swap", key.encode(), make=False)) is None:
            return None
        try:
            with file.open("rb") as f:
                signed, data = f.read(MAC), f.read()
        except OSError:
            return None
        mac.update(data)
        if not hmac.compare_digest(mac.digest(), signed):
            return None   # not this install's
        with contextlib.suppress(OSError):
            os.utime(file)   # used now: the newest kept
        return data

    def put(self, key: str, data: bytes) -> None:
        file = self._file(key)
        if (mac := self.signer.mac(b"swap", key.encode(), make=True)) is None:
            return
        mac.update(data)
        with contextlib.suppress(OSError):
            _write(file, mac.digest(), data)
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
    """``core.gate.STAMPS``: ``{key: the release's name}`` in one JSON file
    (its MAC's hex line under the key in ``key``, then the JSON), its newest
    :data:`STAMPS_KEPT` entries (this process's and another's: the server's
    and the engine's both read and add to it)."""

    def __init__(self, file: Path, key: Path | None = None):
        self.file, self.lock, self.signer = Path(file), threading.Lock(), _Signer(key)

    def _read(self) -> dict[str, str]:
        if (mac := self.signer.mac(b"stamps", make=False)) is None:
            return {}
        try:
            signed, _, body = self.file.read_bytes().partition(b"\n")
            mac.update(body)
            if not hmac.compare_digest(mac.hexdigest().encode(), signed):
                return {}   # not this install's
            kept = json.loads(body)
        except (OSError, ValueError):
            return {}
        return {k: v for k, v in kept.items() if isinstance(v, str)} if isinstance(kept, dict) else {}

    def get(self, key: str) -> str | None:
        return self._read().get(key)

    def put(self, key: str, name: str) -> None:
        with self.lock, contextlib.suppress(OSError):
            if (mac := self.signer.mac(b"stamps", make=True)) is None:
                return
            kept = self._read()
            kept.pop(key, None)
            kept[key] = name   # the newest last
            body = (json.dumps(dict(list(kept.items())[-STAMPS_KEPT:])) + "\n").encode()
            mac.update(body)
            _write(self.file, mac.hexdigest().encode() + b"\n", body)


def install(folder: Path | None = None, key: Path | None = None) -> None:
    """Keep this process's stamps and swap answers in ``folder`` (the user
    cache folder's AzurKit folder), signed under the key in ``key``
    (:func:`key_file`): the app's server and its engine process."""
    from azurkit.core import gate
    from azurkit.tools import characters

    folder = Path(folder) if folder else root()
    gate.STAMPS = Stamps(folder / "stamps.json", key)
    characters.CACHE = Folder(folder / "swap", key=key)

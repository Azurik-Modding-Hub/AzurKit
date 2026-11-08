"""What the app keeps across launches in platformdirs' user cache folder
(Step 4.3i), so a second launch does again none of what a first one worked
out: the images the gate vouched for (``core.gate.STAMPS``: one JSON file,
``stamps.json``, its newest :data:`STAMPS_KEPT` entries, so a picked image
that hasn't changed isn't hashed again) and the store's kinds
(:mod:`azurkit.store`, one folder a kind: the swap's answers,
``tools.characters.CACHE``, and a dress's parts, ``tools.characters.parts.STORE``,
in ``swap/``, so a body dressed once dresses from it, and a copy of it under
another name from its parts), every kind's least recently used removed past one budget in all
(:data:`azurkit.store.BUDGET`). Each is written whole or not at all (a part
file renamed into place); a store that can't be read or written is a store
that holds nothing, as remembering is a convenience. The keys are the
engine's: they name the image's path, size and times, and the swap's code,
recipe, release and earlier layers.

The engine unpickles a character's match and pictures, so the stores trust only what this
install wrote (SEC-4): each entry is sealed by an HMAC-SHA256 under the
install's own key (:func:`key_file`, made once with :mod:`secrets`, in the
user data folder and never the cache folder a shared "speed-up" zip unpacks
into), and so is every kind's, JSON's too, as a planted answer would build
another image. An entry whose seal isn't this key's (planted, or copied
from another install's cache), or any entry once the key is gone, is a
miss: nothing of it is read past its seal, and the answer is worked out
again. The stamps are signed too: the gate takes a stamp for its check of
the image its key names (the path, size, modification and change times),
and where a zip that ships an image can set those (on Windows st_ctime is
the creation time, which an unzipper restores), a forged ``stamps.json``
would vouch for an image the gate never read.

The store's writes go behind the answer (:class:`Kept`): a put hands its
bytes, or what makes them (a dress's ``AZKP1``), to the process's one writer
thread, which makes, seals, writes and prunes them once the call has
answered, and a get of what it hasn't written yet is answered from them.
The thread is a daemon, so a quit never waits on it
(D1012): a write it cuts short leaves a part file, never an entry (a miss
at the next launch), which a later write removes. An answer worked out for
:data:`LONG` or more (a reshape's dress: minutes) is the one exception: its
put waits until the writer has written it (Step 4.4bc), so the call answers
with it kept, and a quit right after (the app's ends its engine process at
once) never loses minutes of work, as A32's third take lost its plan."""

from __future__ import annotations

import contextlib
import hmac
import json
import os
import secrets
import threading
import time
from collections.abc import Callable, Collection
from pathlib import Path

from azurkit import store

STAMPS_KEPT = 64        # the images vouched for, newest kept
KEY = 32                # the install's key, in bytes
LONG = 10.0
"""A swap answer worked out in this many seconds or more, from its get's miss to its put, is written before the put
returns (its write, under a second, a small part of that work); a quicker one is written behind the answer."""
KEEP_WAIT = 60.0        # the most a long answer's put waits on its write (a stalled disk): then it is written behind


def root() -> Path:
    """The user cache folder's AzurKit folder."""
    from platformdirs import user_cache_path
    return user_cache_path("AzurKit", appauthor=False)


def key_file() -> Path:
    """This install's key: ``cache.key`` in the user data folder."""
    from platformdirs import user_data_path
    return user_data_path("AzurKit", appauthor=False) / "cache.key"


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
        part = store.part(file)
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
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

    def seal(self, head: bytes, body: bytes, make: bool) -> bytes | None:
        """The store's seal (:data:`azurkit.store.Seal`): the HMAC of an
        entry's ``head`` and ``body`` under the key."""
        if (mac := self.mac(b"store", head, make=make)) is None:
            return None
        mac.update(body)
        return mac.digest()


class _Made:
    """An entry's bytes, made once, by the writer or a get that came first; ``None`` when they can't be."""

    def __init__(self, make: Callable[[], bytes]):
        self.make, self.lock, self.body = make, threading.Lock(), None

    def __call__(self) -> bytes | None:
        with self.lock:
            make, self.make = self.make, None
            if make is not None:
                with contextlib.suppress(Exception):   # a store that can't make it holds nothing
                    self.body = make()
        return self.body


class _Behind:
    """The process's one writer: each entry a :class:`Kept` puts, written
    after the call that put it has answered, the newest put of a key the
    one written; held (and answered from) until it is."""

    def __init__(self):
        self.lock = threading.Condition()
        self.held: dict[tuple[Path, str, str], tuple[Kept, bytes]] = {}
        self.thread: threading.Thread | None = None

    def put(self, kept: Kept, kind: str, key: str, body: bytes | _Made) -> None:
        with self.lock:
            self.held[(kept.folder, kind, key)] = (kept, body)
            if self.thread is None or not self.thread.is_alive():
                self.thread = threading.Thread(target=self._write, name="azurkit-store", daemon=True)
                self.thread.start()
            self.lock.notify_all()

    def pending(self, folder: Path, kind: str, key: str) -> bytes | None:
        with self.lock:
            held = self.held.get((folder, kind, key))
        return None if held is None else held[1]() if isinstance(held[1], _Made) else held[1]

    def drop(self, folder: Path, kinds: Collection[str] | None) -> None:
        """Forget what it holds of ``kinds`` (every kind) under ``folder``:
        one being written then is removed once written."""
        with self.lock:
            for at in [at for at in self.held if at[0] == folder and (kinds is None or at[1] in kinds)]:
                del self.held[at]

    def settle(self, timeout: float | None) -> bool:
        with self.lock:
            return self.lock.wait_for(lambda: not self.held, timeout)

    def written(self, kept: Kept, kind: str, key: str, body: bytes | _Made, timeout: float) -> bool:
        """Wait until the writer has done with ``body``, put under ``key``
        (written, or refused: a store that can't be written holds nothing),
        ``timeout`` seconds at most; whether it has."""
        at = (kept.folder, kind, key)
        with self.lock:
            return self.lock.wait_for(lambda: (held := self.held.get(at)) is None or held[1] is not body, timeout)

    def _write(self) -> None:
        while True:
            with self.lock:
                self.lock.wait_for(lambda: self.held)
                at, item = next(iter(self.held.items()))
            kept, body = item
            try:
                if (data := body() if isinstance(body, _Made) else body) is not None:
                    kept.write(at[1], at[2], data)
            except Exception:   # a store that can't be written holds nothing; the next put is written as ever
                pass
            with self.lock:
                if self.held.get(at) is item:
                    del self.held[at]
                elif at not in self.held:   # cleared while it was written
                    with contextlib.suppress(OSError):
                        kept.file(at[1], at[2]).unlink(missing_ok=True)
                self.lock.notify_all()


_BEHIND = _Behind()


def settle(timeout: float | None = None) -> bool:
    """Wait for the writer to write all it holds (``timeout`` seconds at
    most); whether it did. Nothing a player does waits on it."""
    return _BEHIND.settle(timeout)


class Kept(store.Store):
    """The app's store under ``folder`` (:func:`root`): every kind's entries
    sealed under the install's key in ``key`` (:func:`key_file`'s by
    default), the least recently used removed past ``most`` bytes in all,
    each put written behind the answer (the process's writer)."""

    def __init__(self, folder: Path, most: int = store.BUDGET, key: Path | None = None):
        self.signer = _Signer(key)
        super().__init__(folder, most, self.signer.seal)

    def get(self, kind: str, key: str) -> object | None:
        self.file(kind, key)
        if (held := _BEHIND.pending(self.folder, kind, key)) is not None:
            return store.decode(kind, held)
        return super().get(kind, key)

    def put(self, kind: str, key: str, value: object, now: bool = False) -> bool:
        """Hand ``value`` to the writer (refused by name first, as
        :func:`azurkit.store.encode` refuses, writing nothing), or a callable
        that gives it, made there, a refusal keeping nothing; it writes it
        after this answers, or, ``now``, before (:data:`KEEP_WAIT` at most)."""
        body = _Made(lambda: store.encode(kind, value())) if callable(value) else store.encode(kind, value)
        self.file(kind, key)
        _BEHIND.put(self, kind, key, body)
        if now:
            _BEHIND.written(self, kind, key, body, KEEP_WAIT)
        return True

    def clear(self, kinds: Collection[str] | None = None) -> list[str]:
        """What :meth:`azurkit.store.Store.clear` removes, and what the writer
        holds of ``kinds`` first."""
        for kind in kinds or ():
            store.form(kind)
        _BEHIND.drop(self.folder, kinds)
        return super().clear(kinds)


class Folder:
    """``tools.characters.CACHE``: the swap's answers (``get(key) -> bytes |
    None``, ``put(key, bytes or what makes them)``), the ``swap`` kind of the
    app's store under ``folder`` (:class:`Kept`, with ``most`` and ``key``).
    A put that answers its own thread's miss of the key :data:`LONG` seconds
    or more before (``characters._kept``'s and ``engine._kept``'s work in
    between, a get and its put on one thread) is written before it returns:
    another call's later miss of that key (the engine runs each call on its
    own thread) never makes a long answer quick."""

    def __init__(self, folder: Path, most: int = store.BUDGET, key: Path | None = None):
        self.kept = Kept(folder, most, key)
        self.missed: dict[tuple[int, str], float] = {}   # a thread's miss of a key, when, until its put answers it

    def get(self, key: str) -> bytes | None:
        if (found := self.kept.get("swap", key)) is None:
            self.missed[threading.get_ident(), key] = time.monotonic()
        return found

    def put(self, key: str, data: bytes | Callable[[], bytes]) -> None:
        missed = self.missed.pop((threading.get_ident(), key), None)
        self.kept.put("swap", key, data, now=missed is not None and time.monotonic() - missed >= LONG)


class Parts:
    """``tools.characters.parts.STORE``: a dress's parts kept across launches
    (Step 4.6o), the ``swap`` kind of the app's store (``kept``, signed),
    each made and written behind the answer: one a quit cuts short is a
    part worked out again (seconds of a dress, not its minutes)."""

    def __init__(self, kept: Kept):
        self.kept = kept

    def get(self, key: str) -> bytes | None:
        return self.kept.get("swap", key)

    def put(self, key: str, make: Callable[[], bytes]) -> None:
        self.kept.put("swap", key, make)

    def used(self, key: str, make: Callable[[], bytes]) -> None:
        """Nothing: a part held here was put here or taken from here, kept by its key."""


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
            store.whole(self.file, mac.hexdigest().encode() + b"\n", body)


def install(folder: Path | None = None, key: Path | None = None) -> None:
    """Keep this process's stamps and the store's kinds in ``folder`` (the
    user cache folder's AzurKit folder), signed under the key in ``key``
    (:func:`key_file`): the app's server and its engine process (the swap's
    answers and a dress's parts, :class:`Parts`)."""
    from azurkit.core import gate
    from azurkit.tools import characters
    from azurkit.tools.characters import parts

    folder = Path(folder) if folder else root()
    gate.STAMPS = Stamps(folder / "stamps.json", key)
    characters.CACHE = Folder(folder, key=key)
    parts.STORE = Parts(characters.CACHE.kept)

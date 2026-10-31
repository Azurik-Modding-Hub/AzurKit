"""Kept answers (Step 4.3x; D1008's kept half, D1015's store): the
engine's small answers that are a pure function of what they are given,
kept as JSON under one complete key, so a host shows one at once (a
reopened tracker, a relaunch's setup and Randomizer tab, a seed tracked
again) and has the engine confirm it.

The calls (:data:`CALLS`): the item tracker's view (``sdk.tracker``), the
setup's restore (``sdk.restore``), the Randomizer tab's answer
(``sdk.randomizer_settings``) and a seed's plan (``sdk.plan``: the plan
store). Each answer is kept under the sha256 (:meth:`Memo.key`) of:

- the code (:func:`code`): AzurKit's version and every file of the
  package (``__pycache__`` and the shipped database, a function of the
  data and planner hashed beside it, left out), and a frozen app's
  executable;
- the randomizer database's key (:func:`database`, ``dbcache.entry``);
- the call and its arguments, canonical (:func:`canonical`: the inputs
  the call reads, as compact JSON with sorted keys);
- the content folder's ``installed.json`` (:func:`installed`).

So a change to any of them is a miss, never a wrong answer. Nothing is kept
with Live on (the app's: its events change the marks), for a tracker ask
that marks (``toggle``) or resets or carries Live's kit or inventory, or for
a refusal. An answer is stored as the engine gave it (its keys in its
order), so a kept one serializes to the bytes the fresh one did;
:meth:`Memo.confirm` works it out again and compares the two
(:func:`digest`), a difference logged as a bug and the engine's answer kept
in its place. An entry holds its call, key and digest: one that doesn't
match them (torn, swapped, another format) is a miss.

The store is the host's (``get(key) -> bytes | None``, ``put(key, bytes)``,
as ``tools.characters.CACHE``'s: the app's signed folder, which a planted
plan can't pass); by default :class:`Mem`, this process's. JSON only, never
a pickle. The site's twin is ``web/memo.mjs``."""

from __future__ import annotations

import contextlib
import functools
import hashlib
import json
import sys
import threading
from collections import OrderedDict
from collections.abc import Callable, Mapping
from pathlib import Path

from azurkit import __version__

FORMAT = 1   # an entry's layout: another is a miss
CALLS = ("tracker", "restore", "randomizer", "plan")
MOST = 64 << 20   # :class:`Mem`'s bytes (a view is about 85 KB, a plan 37 KB, the tab's answer 10 KB)
LIVE_ONLY = ("toggle", "kit")   # a tracker ask that gives one of these (not None) is never kept, as one that
LIVE_TRUE = ("reset", "held")   # sets one of these (the tracker reads them by truth: a falsy one is none)


def _text(value: object, sort: bool) -> str:
    """``value`` as compact JSON (``sort``: its keys sorted); ``ValueError``
    or ``TypeError`` for one JSON can't hold (NaN, a set)."""
    return json.dumps(value, sort_keys=sort, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@functools.cache
def code() -> str:
    """The sha256 of AzurKit's version, every file of the package (its
    path and bytes; ``__pycache__`` and ``tools/randomizer/shipped`` left
    out) and, frozen, the executable's size and time (its modules sit in
    its archive): this process's code key."""
    package = Path(__file__).resolve().parents[1]
    h = hashlib.sha256(f"azurkit {__version__}\0".encode())
    for f in sorted(package.rglob("*")):
        rel = f.relative_to(package)
        if f.is_file() and "__pycache__" not in rel.parts and rel.parts[:3] != ("tools", "randomizer", "shipped"):
            h.update(rel.as_posix().encode() + b"\0" + hashlib.sha256(f.read_bytes()).digest())
    if getattr(sys, "frozen", False):
        at = Path(sys.executable).stat()
        h.update(f"frozen {at.st_size} {at.st_mtime_ns}".encode())
    return h.hexdigest()


@functools.cache
def database() -> str:
    """The randomizer database's key (``dbcache.entry``: its data and the planner's code)."""
    from azurkit.tools.randomizer import dbcache
    from azurkit.tools.randomizer.planner.loader import DATA_DIR

    return dbcache.entry(DATA_DIR).name


def installed() -> str:
    """The sha256 of the content folder's ``installed.json`` as read now (an Install, Update or Remove moves it)."""
    from azurkit.tools.characters import content as kit

    return _sha(json.dumps(kit.installed(), sort_keys=True, separators=(",", ":"), default=str))


def canonical(call: str, args: object) -> str | None:
    """``call``'s arguments as the call reads them, as compact JSON with
    sorted keys, or ``None`` for one never kept: a call not in
    :data:`CALLS`, a tracker ask that marks, resets or carries Live's kit or
    inventory (:data:`LIVE_ONLY`, :data:`LIVE_TRUE`: any kit given, which
    the tracker reads or refuses by name) or one whose marks it refuses (the
    engine names why), or arguments JSON can't hold. A tracker ask's marks
    are read as the tracker reads them (``tracking.marks_of``) and its
    ``spoiler`` and ``gems`` as true or false."""
    if call not in CALLS:
        return None
    if call == "tracker":
        from azurkit.tools.randomizer import tracking

        if not isinstance(args, Mapping) or not set(args) <= set(tracking.GIVEN):
            return None
        if any(args.get(k) is not None for k in LIVE_ONLY) or any(args.get(k) for k in LIVE_TRUE):
            return None
        try:
            marks = tracking.marks_of(args.get("marks"))
        except (TypeError, ValueError):   # tracker.marks' list() and dict() raise TypeError
            return None
        args = {"plan": args.get("plan"), "marks": marks, "spoiler": bool(args.get("spoiler")),
                "gems": bool(args.get("gems"))}
    try:
        return _text(args, True)
    except (TypeError, ValueError):
        return None


def digest(answer: object) -> str:
    """The sha256 of ``answer`` as compact JSON with sorted keys: two answers with one digest are equal."""
    return _sha(_text(answer, True))


def _log(line: str) -> None:
    print(line, file=sys.stderr)


class Mem:
    """This process's store: the newest used entries kept to ``most`` bytes."""

    def __init__(self, most: int = MOST):
        self.most, self.lock, self.kept, self.size = most, threading.Lock(), OrderedDict(), 0

    def get(self, key: str) -> bytes | None:
        with self.lock:
            if (data := self.kept.get(key)) is not None:
                self.kept.move_to_end(key)
            return data

    def put(self, key: str, data: bytes) -> None:
        with self.lock:
            if (old := self.kept.pop(key, None)) is not None:
                self.size -= len(old)
            self.kept[key], self.size = data, self.size + len(data)
            while self.size > self.most and self.kept:
                self.size -= len(self.kept.popitem(last=False)[1])


class Memo:
    """Kept answers in ``store`` (:class:`Mem` by default), a difference a
    confirm finds told to ``log`` (a line to stderr by default)."""

    def __init__(self, store=None, log: Callable[[str], object] | None = None):
        self.store = store if store is not None else Mem()
        self.log = log or _log

    def key(self, call: str, args: object, *, live: bool = False) -> str | None:
        """The key ``call``'s answer for ``args`` is kept under, or ``None``
        when it is never kept (``live``: Live is on; :func:`canonical`)."""
        if live or (text := canonical(call, args)) is None:
            return None
        h = hashlib.sha256()
        for part in (f"azurkit-memo {FORMAT}", code(), database(), call, text, installed()):
            h.update(part.encode() + b"\0")
        return h.hexdigest()

    def _read(self, call: str, key: str) -> object | None:
        try:
            data = self.store.get(key)
            entry = json.loads(data) if data is not None else None
            if (isinstance(entry, dict) and entry.get("format") == FORMAT and entry.get("call") == call
                    and entry.get("key") == key and "answer" in entry
                    and entry.get("sha256") == digest(entry["answer"])):
                return entry["answer"]
        except (OSError, TypeError, ValueError):   # a store that can't be read, or an entry another wrote
            pass
        return None

    def _write(self, call: str, key: str, answer: object) -> None:
        try:
            data = _text({"format": FORMAT, "call": call, "key": key, "sha256": digest(answer), "answer": answer},
                         False).encode()
        except (TypeError, ValueError):   # an answer JSON can't hold is never kept
            return
        with contextlib.suppress(OSError):   # remembering is a convenience
            self.store.put(key, data)

    def get(self, call: str, args: object, *, live: bool = False) -> object | None:
        """``call``'s kept answer for ``args``, or ``None``."""
        key = self.key(call, args, live=live)
        return None if key is None else self._read(call, key)

    def put(self, call: str, args: object, answer: object, *, live: bool = False) -> None:
        """Keep ``answer`` as ``call``'s for ``args`` (nothing when it is never kept)."""
        if (key := self.key(call, args, live=live)) is not None:
            self._write(call, key, answer)

    def answer(self, call: str, args: object, work: Callable[[], object], *, live: bool = False) -> tuple[object, bool]:
        """``(the answer, whether it was kept)``: the kept answer for
        ``args``, else ``work()``'s (its refusal raised, never kept), kept
        under the key its inputs had as it started."""
        key = self.key(call, args, live=live)
        if key is not None and (kept := self._read(call, key)) is not None:
            return kept, True
        fresh = work()
        if key is not None:
            self._write(call, key, fresh)
        return fresh, False

    def confirm(self, call: str, args: object, kept: object, work: Callable[[], object], *,
                live: bool = False) -> object:
        """``work()``'s answer, which a host shows in place of ``kept`` (a
        kept answer it showed for ``args``): equal by construction, so a
        difference is a bug, logged by both digests and kept no more (the
        engine's answer is kept in its place)."""
        key = self.key(call, args, live=live)
        fresh = work()
        if (was := digest(kept)) != (now := digest(fresh)):
            self.log(f"azurkit: a kept {call} answer ({was[:12]}) differs from the engine's ({now[:12]}): "
                     "a bug, the engine's is kept")
            if key is not None:
                self._write(call, key, fresh)
        return fresh

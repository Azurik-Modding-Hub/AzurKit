"""A dress's parts kept by content, in this process (Step 4.6n, the Check
design's L1): the stages of a variant's dress whose output is a function of
what they read alone, each kept under a key of those reads and taken in
place of working it out again, so a second copy of a variant under any
name (New from this, a Check of it) dresses only the glue between them.

The stages: the body's W24 mesh, W29 rig and W30 paint
(``_player_character._variant_body``, three parts, each keyed on the one
before: an edit to the paint keeps the mesh and the rig), the size a body
is folded with (``size_shape``), W28's two restyles (the arms' and the
springs', ``_player_variants.restyled``), the LOD and shadow cuts
(``decimate._taken``) and their writes (``decimate.screen_lods`` and
``shadow_lod``). Each key is name-free and path-free: the bytes a stage
reads (a file by its sha256, :func:`digest`), the recipe fields it reads
by ``repr`` (a zero's sign counts) and each file it reads in its folder by
its bytes (:func:`stamps`), never the variant's name, its folder or its
recipe file's path, which reach only its sounds and its log (the design's
F5), and never its refusal: a stage that raises keeps nothing, so a
refusal (which names the variant) is worked out again.

A part's file is kept as the pages where it differs from the file the dress
handed the stage (:func:`delta`), so a kept part holds no second copy of
the 70 MB ``characters.xbr``; its objects (a mesh plan, a rig, the cuts)
pickled (:func:`dump`), so each taker gets its own (:func:`load`, which
unpickles nothing else). The parts held are bounded by
:data:`ROOM`, the least recently taken let go first, under :data:`LOCK`
(the app's engine dresses on a thread a call, so two dresses may take and
keep at once). The answer a part gives is the one the stage would work
out, byte for byte: what a stage reads is all in its key, and the stage is
a function of it.

A host keeps them across visits too (Step 4.6o, the design's L2): each part
kept is handed to :data:`STORE` as :mod:`.part_codec` keeps it (no pickle;
a stale one refused by name), under its key and the code's digest
(``characters._code()``, so another version's never answers), and a part
this process doesn't hold is asked of it before it is worked out. The
app's store is its signed ``swap`` kind, written behind the answer; the
site's, the parts IndexedDB kept for a recipe's content, which the page
offers with a Check and keeps after its answer.

And a part neither holds is asked of what ships (Step 4.6p, the design's
L3): ``shipped.part``, the parts ``scripts/record_shipped.py`` recorded
from a Check of each built-in and of its own copy, listed with the entry
(its ``shipped/parts/`` folder) but left by Install for the Check that
asks for one, which fetches it then from the entry's source on every
host, so their first Check needs no dress. A part fetched so is handed to
:data:`STORE` as one made here (a later visit fetches none); one a content
folder holds (a clone's) is never; and a fresh one is heard
(``shipped.SEEN``) for the re-record pin."""

from __future__ import annotations

import contextlib
import hashlib
import io
import pickle
from collections import OrderedDict
from pathlib import Path

OFF = False
"""``True``: no part is kept or taken, so every stage is worked out (a fresh dress, the pin's)."""
ROOM = 256 << 20
"""The bytes the kept parts may hold, at most (the design's R5: a few hundred MB in process)."""
PAGE = 4096
"""The bytes a part's file is compared and kept in: each page that differs from the stage's input (:func:`delta`)."""
HEARD: dict[str, dict[str, int]] | None = None
"""A dict: each stage's parts taken (``hit``; of them ``stored``, from :data:`STORE`, ``shipped`` and ``fetched``) and
worked out (``miss``), by stage name (a test's, a measure's)."""

STORE = None
"""A host's store of parts across visits (``get(key) -> bytes | None``, ``put(key, bytes or what makes them)``, made
behind the answer, and ``used(key, what makes its bytes)``: a part this process held, taken again, so the site keeps
it for the content asking too), or ``None``: kept in this process only."""

LOCK: contextlib.AbstractContextManager = contextlib.nullcontext()
"""Held over the kept parts by :func:`get`, :func:`held`, :func:`put` and :func:`clear`: none here (the engine holds
no threads); the app's engine sets a lock, as it runs each call on a thread of its own."""

_SLOTS: OrderedDict[str, tuple[object, int]] = OrderedDict()
_HELD = [0]
_SHIPPED: set[str] = set()   # the parts held here that were taken from what ships: never handed to STORE


def key(stage: str, *reads: object) -> str:
    """A part's key: ``stage`` and each of ``reads`` (digests, names, numbers,
    specs) by ``repr``, so ``-0.0`` and ``0.0`` are two keys."""
    h = hashlib.sha256(stage.encode())
    for read in reads:
        if isinstance(read, (bytes, bytearray, memoryview)):
            raise TypeError(f"parts.key({stage!r}): a file goes in by its digest")
        h.update(b"\0" + repr(read).encode())
    return f"{stage}:{h.hexdigest()}"


def digest(data: bytes) -> str:
    """The sha256 of ``data``: the manifest's, unhashed, where ``data`` is a
    file the swap's build read from the image and checked (``ports.Vanilla``)."""
    from azurkit.tools.characters import ports

    build = ports._BUILD.get()
    if build is not None and (known := build.vanilla.digest_of(data)) is not None:
        return known
    return hashlib.sha256(data).hexdigest()


class Pickled(bytes):
    """An object a part holds, pickled in this process (:func:`dump`): kept
    across visits as the values it holds (:mod:`.part_codec`), never as a pickle."""


def dump(obj: object) -> Pickled:
    """``obj`` as a part holds it: its pickle, so each taker unpickles its own copy."""
    return Pickled(pickle.dumps(obj, pickle.HIGHEST_PROTOCOL))


def load(held: object) -> object:
    """The object :func:`dump` pickled as ``held``: every taker of a held
    part unpickles here, and only a :class:`Pickled` (this process's own
    :func:`dump`, or :mod:`.part_codec`'s of the values it read back), any
    other value refused by its type's name before anything unpickles it."""
    if type(held) is not Pickled:
        kind = type(held)
        raise TypeError(f"parts.load: a held part's object is a {kind.__module__}.{kind.__qualname__}, "
                        "not a parts.Pickled this process made: not unpickled")
    return pickle.loads(held)


def since(ref: bytes, ref_key: str | None, out: bytes) -> str:
    """``out``'s name by content with no hash of all of it (Step 4.6q, the
    Check design's chained keys): ``ref_key`` (``ref``'s: a part's key, or
    its digest) and the pages where ``out`` differs from ``ref``
    (:func:`delta`'s runs), those hashed; a dress's later files share
    most of their pages with the one its body's parts left, so two files
    of one name are one file. Its sha256 (:func:`digest`) where most of it
    differs, or ``ref_key`` is ``None``."""
    if ref_key is None:
        return digest(out)
    size, spans, pages = delta(ref, out)
    if size is None:
        return digest(out)
    return key("since", ref_key, size, tuple(spans), hashlib.sha256(pages).hexdigest())


def pickled(obj: object) -> str:
    """The sha256 of ``obj``'s pickle: an object a stage reads, by its
    content. Pickled with no memo, so a value held in two places is written
    each time: an object read back from :data:`STORE` (:mod:`.part_codec`
    makes a tuple or a string held twice two) names as the one kept."""
    out = io.BytesIO()
    pickler = pickle.Pickler(out, pickle.HIGHEST_PROTOCOL)
    pickler.fast = True
    pickler.dump(obj)
    return hashlib.sha256(out.getbuffer()).hexdigest()


def stamps(folder: Path | None, files) -> tuple:
    """Each of ``files`` (names in ``folder``, the recipe's) by the sha256
    a dress reads it as (a glTF's with its buffers, ``mesh_edit.file_sha256``;
    ``None`` where it can't be read), never by the folder's path."""
    from azurkit.tools.characters import mesh_edit

    out = []
    for name in sorted(set(files)):
        path = Path(folder or ".") / name
        try:
            if path.suffix.casefold() in (".gltf", ".glb"):
                try:
                    out.append((name, mesh_edit.file_sha256(path)))
                    continue
                except ValueError:   # not a glTF the dress reads: its bytes
                    pass
            out.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))
        except OSError:
            out.append((name, None))
    return tuple(out)


def _heard(stage: str, how: str) -> None:
    if HEARD is not None:
        counts = HEARD.setdefault(stage, {"hit": 0, "miss": 0})
        counts[how] = counts.get(how, 0) + 1


def _stored(name: str) -> str:
    """The key :data:`STORE` keeps the part named ``name`` under: with the code's digest, so another version misses."""
    from azurkit.tools import characters

    return hashlib.sha256(f"part\0{characters._code()}\0{name}".encode()).hexdigest()


def _fetch(name: str) -> tuple[object, int, str] | None:
    """The part :data:`STORE` keeps under ``name``, else the one shipped
    (``shipped.part``), its size and where it came from (``stored``,
    ``shipped`` from the content folder, or ``fetched`` from its entry's
    source, then handed to :data:`STORE` as a part made here, so a later
    visit fetches none), held in this process again; ``None`` where neither
    has one, or none this codec reads."""
    from azurkit.tools.characters import part_codec, shipped

    blob, came = None if STORE is None else STORE.get(_stored(name)), "stored"
    if blob is None and (found := shipped.part(name)) is not None:
        blob, came = found[0], "fetched" if found[1] else "shipped"
    if blob is None:
        return None
    try:
        part, size = part_codec.decode(blob)
    except (ValueError, TypeError):   # a stale or spoiled part: worked out again
        return None
    _hold(name, part, size)
    if came == "shipped":
        with LOCK:
            _SHIPPED.add(name)
    elif came == "fetched" and STORE is not None:
        STORE.put(_stored(name), blob)
    return part, size, came


def get(name: str, stage: str | None = None) -> object | None:
    """The part kept under ``name``, here or in :data:`STORE`, or ``None``
    (``stage``: heard as taken or not, and as taken from the store); one
    held here is told to :data:`STORE` as used."""
    with LOCK:
        found = None if OFF else _SLOTS.get(name)
        if found is not None:
            _SLOTS.move_to_end(name)
        shipped = name in _SHIPPED
    if found is not None and STORE is not None and not shipped:
        from azurkit.tools.characters import part_codec

        STORE.used(_stored(name), lambda held=found: part_codec.encode(held))
    came = found is None and not OFF and (found := _fetch(name)) is not None and found[2]
    if stage is not None:
        with LOCK:
            _heard(stage, "miss" if found is None else "hit")
            if came:
                _heard(stage, came)
    return None if found is None else found[0]


def held(name: str) -> bool:
    """Whether a part is kept under ``name``, here or in :data:`STORE` (taken
    into this process then; none heard)."""
    with LOCK:
        if OFF or name in _SLOTS:
            return not OFF
    return _fetch(name) is not None


def put(name: str, part: object, size: int) -> None:
    """Keep ``part`` (``size`` bytes) under ``name``, letting the least
    recently taken go past :data:`ROOM`, and hand it to :data:`STORE` (and
    to ``shipped.SEEN``, the pin's); one larger than :data:`ROOM` is not kept."""
    from azurkit.tools.characters import shipped

    if OFF or size > ROOM:
        return
    _hold(name, part, size)
    shipped.heard_part(name, part, size)
    if STORE is not None:
        from azurkit.tools.characters import part_codec

        STORE.put(_stored(name), lambda: part_codec.encode((part, size)))


def _hold(name: str, part: object, size: int) -> None:
    with LOCK:
        if (old := _SLOTS.pop(name, None)) is not None:
            _HELD[0] -= old[1]
        _SHIPPED.discard(name)
        _SLOTS[name] = (part, size)
        _HELD[0] += size
        while _HELD[0] > ROOM and _SLOTS:
            _HELD[0] -= _SLOTS.popitem(last=False)[1][1]


def clear() -> None:
    """Let every kept part go."""
    with LOCK:
        _SLOTS.clear()
        _SHIPPED.clear()
        _HELD[0] = 0


def delta(ref: bytes, out: bytes) -> tuple:
    """``out`` as the :data:`PAGE`-sized pages where it differs from ``ref``
    (past ``ref``'s end: all of it), found 8 bytes at a time (numpy) with no
    copy of either file: ``(len(out), spans, pages)``, ``spans`` each run's
    start and end (``array("q")``) and ``pages`` their bytes, one block each
    (a dress's heap holds a part in two pieces, not one a run), or ``(None,
    None, out)`` whole where they would hold most of it (:func:`undelta`
    gives ``out`` back from ``ref``)."""
    from array import array

    import numpy as np

    size, same = len(out), min(len(ref), len(out))
    full = same // PAGE * PAGE
    at = np.flatnonzero((np.frombuffer(ref, np.uint64, full // 8).reshape(-1, PAGE // 8)
                         != np.frombuffer(out, np.uint64, full // 8).reshape(-1, PAGE // 8)).any(axis=1))
    breaks = np.flatnonzero(np.diff(at) != 1)   # consecutive pages are one run
    spans = array("q")
    if len(at):
        spans.extend(np.column_stack((at[np.r_[0, breaks + 1]] * PAGE,
                                      (at[np.r_[breaks, len(at) - 1]] + 1) * PAGE)).ravel().tolist())
    if ref[full:same] != out[full:same]:
        spans.extend((full, same))
    if size > same:
        spans.extend((same, size))
    if sum(spans[1::2]) - sum(spans[::2]) > size // 2:
        return None, None, bytes(out)
    view = memoryview(out)
    return size, spans, b"".join(view[spans[k]:spans[k + 1]] for k in range(0, len(spans), 2))


def undelta(ref: bytes, part: tuple) -> bytes:
    """The file :func:`delta` kept ``part`` of, over ``ref``: one copy, ``ref``'s pages between its runs."""
    size, spans, pages = part
    if size is None:
        return pages
    view, held, pieces, at, used = memoryview(ref), memoryview(pages), [], 0, 0
    for k in range(0, len(spans), 2):
        start, end = spans[k], spans[k + 1]
        pieces += [view[at:start], held[used:used + end - start]]
        at, used = end, used + end - start
    pieces.append(view[at:size])
    return b"".join(pieces)


def size_of(part: tuple) -> int:
    """The bytes :func:`delta`'s ``part`` holds."""
    _, spans, pages = part
    return len(pages) + (0 if spans is None else spans.itemsize * len(spans))


__all__ = ["HEARD", "LOCK", "OFF", "PAGE", "ROOM", "STORE", "Pickled", "clear", "delta", "digest", "dump", "get",
           "held", "key", "load", "pickled", "put", "since", "size_of", "stamps", "undelta"]

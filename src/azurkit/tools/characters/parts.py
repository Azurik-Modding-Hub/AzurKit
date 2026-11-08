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
pickled, so each taker gets its own. The parts held are bounded by
:data:`ROOM`, the least recently taken let go first. The answer a part
gives is the one the stage would work out, byte for byte: what a stage
reads is all in its key, and the stage is a function of it."""

from __future__ import annotations

import hashlib
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
"""A dict: each stage's parts taken (``hit``) and worked out (``miss``), by stage name (a test's, a measure's)."""

_SLOTS: OrderedDict[str, tuple[object, int]] = OrderedDict()
_HELD = [0]


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


def pickled(obj: object) -> str:
    """The sha256 of ``obj``'s pickle: an object a stage reads, by its content."""
    return hashlib.sha256(pickle.dumps(obj, pickle.HIGHEST_PROTOCOL)).hexdigest()


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
        counts[how] += 1


def get(name: str, stage: str | None = None) -> object | None:
    """The part kept under ``name``, or ``None`` (``stage``: heard as taken or not)."""
    found = None if OFF else _SLOTS.get(name)
    if found is not None:
        _SLOTS.move_to_end(name)
    if stage is not None:
        _heard(stage, "miss" if found is None else "hit")
    return None if found is None else found[0]


def held(name: str) -> bool:
    """Whether a part is kept under ``name`` (none taken, none heard)."""
    return not OFF and name in _SLOTS


def put(name: str, part: object, size: int) -> None:
    """Keep ``part`` (``size`` bytes) under ``name``, letting the least
    recently taken go past :data:`ROOM`; one larger than it is not kept."""
    if OFF or size > ROOM:
        return
    if (old := _SLOTS.pop(name, None)) is not None:
        _HELD[0] -= old[1]
    _SLOTS[name] = (part, size)
    _HELD[0] += size
    while _HELD[0] > ROOM and _SLOTS:
        _HELD[0] -= _SLOTS.popitem(last=False)[1][1]


def clear() -> None:
    """Let every kept part go."""
    _SLOTS.clear()
    _HELD[0] = 0


def delta(ref: bytes, out: bytes) -> tuple:
    """``out`` as the :data:`PAGE`-sized pages where it differs from ``ref``
    (past ``ref``'s end: all of it), ``(len(out), ((start, bytes), ...))``,
    found 8 bytes at a time (numpy) with no copy of either file, or ``(None,
    out)`` whole where they would hold most of it (:func:`undelta` gives
    ``out`` back from ``ref``)."""
    import numpy as np

    size, same = len(out), min(len(ref), len(out))
    full = same // PAGE * PAGE
    pages = (np.frombuffer(ref, np.uint64, full // 8).reshape(-1, PAGE // 8)
             != np.frombuffer(out, np.uint64, full // 8).reshape(-1, PAGE // 8)).any(axis=1)
    at = np.flatnonzero(pages)
    cuts = np.flatnonzero(np.diff(at) != 1) + 1   # consecutive pages are one run
    runs = [(int(run[0]) * PAGE, (int(run[-1]) + 1) * PAGE) for run in np.split(at, cuts) if len(run)]
    if ref[full:same] != out[full:same]:
        runs.append((full, same))
    if size > same:
        runs.append((same, size))
    if sum(end - start for start, end in runs) * 2 > size:
        return None, bytes(out)
    return size, tuple((start, bytes(out[start:end])) for start, end in runs)


def undelta(ref: bytes, part: tuple) -> bytes:
    """The file :func:`delta` kept ``part`` of, over ``ref``: one copy, ``ref``'s pages between its runs."""
    size, runs = part
    if size is None:
        return runs
    view, pieces, at = memoryview(ref), [], 0
    for start, data in runs:
        pieces += [view[at:start], data]
        at = start + len(data)
    pieces.append(view[at:size])
    return b"".join(pieces)


def size_of(part: tuple) -> int:
    """The bytes :func:`delta`'s ``part`` holds."""
    size, runs = part
    return len(runs) if size is None else sum(len(data) for _, data in runs)


__all__ = ["HEARD", "OFF", "PAGE", "ROOM", "clear", "delta", "digest", "get", "held", "key", "pickled", "put",
           "size_of", "stamps", "undelta"]

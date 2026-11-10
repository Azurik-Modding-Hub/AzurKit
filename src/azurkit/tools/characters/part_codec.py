"""A dress's kept parts as bytes a later visit reads back (Step 4.6o, the
Check design's L2): the safe codec :mod:`.parts` keeps them across visits in
(the app's signed store, the site's IndexedDB), never a pickle (D992's
SEC-5): reading one runs no code, it only makes the values it lists.

A part is what a stage keeps (:mod:`.parts`): tuples of numbers, strings,
bytes, ``array`` runs and the objects it pickles in its process
(:class:`.parts.Pickled`: a mesh plan, a rig, LODs, a size), each kept here
as the values it holds: ``None``, bools, ints, floats (their bits: a zero's
sign and a NaN's payload stand), strings, bytes, lists, tuples, sets,
dicts (in their order), ``array`` and numpy arrays and numbers of fixed
widths, and the dataclasses of this package's modules that hold the parts
(:data:`MODULES`), each by its fields. A list, dict, set or object held in
two places is one again when read back, as pickle keeps it. A run of
numbers, or of tuples of them nested alike (a mesh's vertices, its
triangles' corners), of bytes, of dicts or of one frozen dataclass is kept
in columns (``array``'s bytes), so a mesh's hundred
thousand vertices read back in a few calls.

The bytes: :data:`MAGIC`, the length the rest inflates to (at most
:data:`MOST`), then a zstd frame of a JSON head (the codec's
:data:`FORMAT` and each class's module, name and fields) and the values.
They are read back only whole: a format or a class's fields that aren't
this AzurKit's (a stale part: its class changed since) is refused by name,
as is any other class, a length past the bytes there are, or bytes past
the last value (``ValueError``); the store keeps parts under the code's
digest too, so another version never asks for one."""

from __future__ import annotations

import dataclasses
import importlib
import json
import pickle
import struct
import sys
from array import array
from itertools import accumulate, chain

MAGIC = b"AZPT1\0"
FORMAT = 1
LEVEL = 3
"""The zstd level a part is kept at (fast to make behind the answer; a body's pages compress little more at 19)."""
MOST = 1 << 29
"""The bytes a kept part may inflate to, at most (twice the parts a process holds, :data:`.parts.ROOM`)."""
DEPTH = 100
"""How deep a part's values may nest."""
MODULES = frozenset(f"azurkit.tools.characters.{m}" for m in (
    "_player_character", "_player_variants", "body_codec", "characters", "decimate", "jiggle", "jiggle_rt",
    "mesh_edit", "paint", "lods", "gltf_import", "clip_import", "retarget", "skeleton"))
"""The modules whose dataclasses a part may hold."""
ARRAYS = "bBhHiIqQfd"
"""The ``array`` type codes a part may hold: each one's width the same on every host (``l`` is 4 bytes in wasm)."""
RUN = 4
"""The least items a run is kept in columns at."""

_U32, _U64, _I64, _F64 = struct.Struct("<I"), struct.Struct("<Q"), struct.Struct("<q"), struct.Struct("<d")
_LITTLE = sys.byteorder == "little"
_PICKLED = ("azurkit.tools.characters.parts", "Pickled")
(_NONE, _TRUE, _FALSE, _INT, _BIG, _FLOAT, _STR, _BYTES, _PICKLE, _REF, _TUPLE, _LIST, _FROZEN, _SET, _DICT, _BARRAY,
 _ARRAY, _NDARRAY, _NUMBER, _OBJECT, _NUMBERS, _WIDE, _DICTS, _OBJECTS) = b"NTFiIdsbP@tlfemBangcRKMC"


class _Writer:
    def __init__(self):
        self.out: list[bytes] = []
        self.memo: dict[int, int] = {}
        self.held: list = []   # each object memo names, so its id isn't another's while this writes
        self.classes: dict[type, int] = {}

    def cls(self, cls: type) -> int:
        if (at := self.classes.get(cls)) is None:
            if cls.__module__ not in MODULES or not dataclasses.is_dataclass(cls) or "<locals>" in cls.__qualname__:
                raise ValueError(f"kept part: no codec for a {cls.__module__}.{cls.__qualname__}")
            at = self.classes[cls] = len(self.classes)
        return at

    def seen(self, x) -> bool:
        """Whether ``x`` (a mutable value) was written before (a reference then written), else noted."""
        if (at := self.memo.get(id(x))) is not None:
            self.out.append(bytes([_REF]) + _U32.pack(at))
            return True
        self.memo[id(x)] = len(self.memo)
        self.held.append(x)
        return False

    def run(self, seq, kind: int, depth: int) -> bool:
        """``seq`` (a list or tuple, ``kind`` its tag) in columns, where it is a run of numbers or of tuples of
        them nested alike, of bytes, of dicts or of one frozen dataclass; whether it was."""
        if len(seq) < RUN:
            return False
        types = set(map(type, seq))
        if len(types) != 1:
            return False
        t = types.pop()
        if t is float or t is int or t is tuple:
            dims, level = [len(seq)], seq
            while t is tuple:
                widths = set(map(len, level))
                if len(widths) != 1 or (w := widths.pop()) == 0 or len(dims) == 8:
                    return False
                dims.append(w)
                level = list(chain.from_iterable(level))
                types = set(map(type, level))
                if len(types) != 1:
                    return False
                t = types.pop()
            if t is not float and t is not int:
                return False
            try:
                raw = array("d" if t is float else "q", level)
            except OverflowError:
                return False
            self.out += [bytes([_NUMBERS, kind, ord("d" if t is float else "q"), len(dims)]),
                         *map(_U32.pack, dims), raw.tobytes()]
            return True
        if t is bytes:
            self.out += [bytes([_WIDE, kind])]
            self.value(tuple(map(len, seq)), depth + 1)
            self.out.append(b"".join(seq))
            return True
        if t is dict:   # each a reference to one written before (in it too), or fresh: their items in columns
            refs, fresh = [], []
            for d in seq:
                if (at := self.memo.get(id(d))) is None:
                    self.memo[id(d)] = at = len(self.memo)
                    self.held.append(d)
                    fresh.append(d)
                    refs.append(-1)
                else:
                    refs.append(at)
            self.out.append(bytes([_DICTS, kind]))
            for column in (refs, map(len, fresh), chain.from_iterable(fresh),
                           chain.from_iterable(map(dict.values, fresh))):
                self.value(tuple(column), depth + 1)
            return True
        params = getattr(t, "__dataclass_params__", None)
        if params is None or not params.frozen or hasattr(t, "__slots__"):
            return False
        names = [f.name for f in dataclasses.fields(t)]
        if any(vars(o).keys() != set(names) for o in seq):
            return False   # one holds other than its fields: each written alone refuses it
        self.out += [bytes([_OBJECTS, kind]), _U32.pack(self.cls(t)), _U32.pack(len(seq))]
        for name in names:
            self.value(tuple(getattr(o, name) for o in seq), depth + 1)
        return True

    def value(self, x, depth: int) -> None:
        if depth > DEPTH:
            raise ValueError(f"kept part: its values nest past {DEPTH} deep")
        out, t = self.out, type(x)
        if x is None:
            out.append(b"N")
        elif t is bool:
            out.append(b"T" if x else b"F")
        elif t is int:
            if -(1 << 63) <= x < (1 << 63):
                out += [b"i", _I64.pack(x)]
            else:
                raw = x.to_bytes((x.bit_length() + 8) // 8, "little", signed=True)
                out += [b"I", _U32.pack(len(raw)), raw]
        elif t is float:
            out += [b"d", _F64.pack(x)]
        elif t is str:
            raw = x.encode("utf-8", "surrogatepass")
            out += [b"s", _U32.pack(len(raw)), raw]
        elif t is bytes:
            out += [b"b", _U64.pack(len(x)), x]
        elif t is tuple:
            if not self.run(x, _TUPLE, depth):
                out += [b"t", _U32.pack(len(x))]
                for v in x:
                    self.value(v, depth + 1)
        elif t is list:
            if self.seen(x):
                return
            if not self.run(x, _LIST, depth):
                out += [b"l", _U32.pack(len(x))]
                for v in x:
                    self.value(v, depth + 1)
        elif t is dict:
            if self.seen(x):
                return
            out.append(b"m")
            self.value(tuple(x), depth + 1)
            self.value(tuple(x.values()), depth + 1)
        elif t is frozenset or t is set:
            if t is set and self.seen(x):
                return
            out.append(b"f" if t is frozenset else b"e")
            self.value(tuple(sorted(x, key=_order)), depth + 1)   # one order in every process (a str's hash isn't)
        elif (t.__module__, t.__name__) == _PICKLED:   # an object its process pickled (its own): what it holds
            from azurkit.tools.characters import parts

            out.append(b"P")
            self.value(parts.load(x), depth + 1)
        elif t is bytearray:
            if not self.seen(x):
                out += [b"B", _U64.pack(len(x)), bytes(x)]
        elif t is array:
            if x.typecode not in ARRAYS:
                raise ValueError(f"kept part: no codec for an array of {x.typecode!r}")
            if not self.seen(x):
                out += [b"a", x.typecode.encode(), _U64.pack(len(x) * x.itemsize), x.tobytes()]
        elif t.__module__ == "numpy" and t.__name__ == "ndarray":
            if not self.seen(x):
                dtype = _dtype(x.dtype)
                out += [b"n", _U32.pack(len(dtype)), dtype, bytes([x.ndim]), *map(_U64.pack, x.shape),
                        x.tobytes(order="C")]
        elif t.__module__ == "numpy" and getattr(x, "shape", None) == () and hasattr(x, "dtype"):
            dtype = _dtype(x.dtype)
            out += [b"g", _U32.pack(len(dtype)), dtype, x.tobytes()]
        elif hasattr(t, "__dataclass_fields__"):
            if not t.__dataclass_params__.frozen and self.seen(x):
                return
            names = [f.name for f in dataclasses.fields(t)]
            if hasattr(x, "__dict__") and vars(x).keys() != set(names):
                raise ValueError(f"kept part: a {t.__qualname__} holds other than its fields")
            out += [b"c", _U32.pack(self.cls(t))]
            for name in names:
                self.value(getattr(x, name), depth + 1)
        else:
            raise ValueError(f"kept part: no codec for a {t.__module__}.{t.__qualname__}")


def _dtype(dtype) -> bytes:
    if dtype.kind not in "biufc" or dtype.byteorder == ">" or dtype.hasobject:
        raise ValueError(f"kept part: no codec for a numpy {dtype.str} array")
    return dtype.str.encode()


def _order(x) -> tuple[str, str]:
    """A set's items' order: by type and ``repr``, the same in every process."""
    return type(x).__qualname__, repr(x)


def _body(part: object) -> bytes:
    if not _LITTLE:
        raise ValueError("kept part: only a little-endian host keeps parts")
    w = _Writer()
    w.value(part, 0)
    head = json.dumps({"format": FORMAT, "classes": [
        [c.__module__, c.__qualname__, [f.name for f in dataclasses.fields(c)]] for c in w.classes]},
        separators=(",", ":")).encode()
    body = b"".join([_U32.pack(len(head)), head, *w.out])
    if len(body) > MOST:
        raise ValueError(f"kept part: {len(body):,} bytes, past the {MOST:,} a part may hold")
    return body


def encode(part: object, level: int = LEVEL) -> bytes:
    """``part`` as :mod:`.parts` keeps it across visits (zstd at ``level``;
    a shipped one's at 19, ``scripts/record_shipped.py``'s), or
    ``ValueError`` naming a value the codec doesn't keep (nothing is kept then)."""
    from compression import zstd

    body = _body(part)
    options = {zstd.CompressionParameter.compression_level: level,
               zstd.CompressionParameter.enable_long_distance_matching: int(level > LEVEL)}
    return MAGIC + _U64.pack(len(body)) + zstd.compress(body, options=options)


def digest(part: object) -> str:
    """The sha256 of the values ``part`` holds as this codec lists them
    (before zstd, whose bytes a library's version may move): the same
    part's in every process of this host (a set's items in one order), the
    shipped one's answer (``shipped.py``'s ``part`` rows)."""
    import hashlib

    return hashlib.sha256(_body(part)).hexdigest()


def _made(cls, names: list[str], values, obj: object = None) -> object:
    """An object of ``cls`` holding ``values`` in its fields ``names``: no code of its runs (as pickle makes one)."""
    obj = object.__new__(cls) if obj is None else obj
    if hasattr(obj, "__dict__"):
        obj.__dict__.update(zip(names, values))
    else:
        for name, v in zip(names, values):
            object.__setattr__(obj, name, v)
    return obj


class _Reader:
    def __init__(self, data: bytes, classes: list):
        self.data, self.at, self.memo, self.classes = data, 0, [], classes

    def take(self, n: int) -> bytes:
        if n < 0 or self.at + n > len(self.data):
            raise ValueError("kept part: its values end early")
        self.at += n
        return self.data[self.at - n:self.at]

    def u32(self) -> int:
        at = self.at
        self.at += 4
        return _U32.unpack_from(self.data, at)[0]

    def count(self, least: int = 1) -> int:
        """A count of items each at least ``least`` bytes, never past the bytes left."""
        n = self.u32()
        if n * least > len(self.data) - self.at:
            raise ValueError(f"kept part: {n:,} items past the bytes left")
        return n

    def cls(self) -> tuple[type, list[str]]:
        at = self.u32()
        if at >= len(self.classes):
            raise ValueError(f"kept part: no class {at}")
        return self.classes[at]

    def run(self, tag: int, depth: int):
        kind = self.take(1)[0]
        if kind != _LIST and kind != _TUPLE:
            raise ValueError(f"kept part: a run of {kind}")
        out = [] if kind == _LIST else None
        if out is not None:
            self.memo.append(out)
        if tag == _NUMBERS:
            code, ndim = chr(self.take(1)[0]), self.take(1)[0]
            if code not in "dq" or not 1 <= ndim <= 8:
                raise ValueError(f"kept part: a run of {code!r} in {ndim} dimensions")
            dims, size = [self.u32() for _ in range(ndim)], 8
            for d in dims:
                size *= d
            items = array(code)
            items.frombytes(self.take(size))
            items = items.tolist()
            for w in reversed(dims[1:]):   # each innermost tuple from its run of items
                items = list(zip(*[iter(items)] * w))
        elif tag == _WIDE:
            sizes = self.value(depth + 1)
            if type(sizes) is not tuple or any(type(n) is not int or n < 0 for n in sizes):
                raise ValueError("kept part: a run of bytes' lengths aren't counts")
            raw, ends = self.take(sum(sizes)), list(accumulate(sizes))
            items = [raw[a:b] for a, b in zip([0, *ends], ends)]
        elif tag == _DICTS:
            refs, items, fresh = self.value(depth + 1), [], []
            if type(refs) is not tuple:
                raise ValueError("kept part: a run of dicts' references aren't a tuple")
            for ref in refs:
                if type(ref) is not int or ref >= len(self.memo):
                    raise ValueError(f"kept part: no value {ref} before it")
                if ref < 0:
                    fresh.append({})
                    self.memo.append(fresh[-1])
                items.append(fresh[-1] if ref < 0 else self.memo[ref])
            sizes, keys, values = (self.value(depth + 1) for _ in range(3))
            if not (type(sizes) is type(keys) is type(values) is tuple and len(sizes) == len(fresh)
                    and len(keys) == len(values) == sum(sizes)):
                raise ValueError("kept part: a run of dicts' keys aren't their values'")
            at = 0
            for d, k in zip(fresh, sizes):
                d.update(zip(keys[at:at + k], values[at:at + k]))
                at += k
        else:
            (cls, names), n = self.cls(), self.u32()
            columns = [self.value(depth + 1) for _ in names]
            if any(type(c) is not tuple or len(c) != n for c in columns):
                raise ValueError(f"kept part: a run of {cls.__qualname__}'s columns aren't {n:,} long")
            items = [_made(cls, names, row) for row in zip(*columns)] if names else [_made(cls, (), ())
                                                                                   for _ in range(n)]
        if out is None:
            return tuple(items)
        out += items
        return out

    def value(self, depth: int):
        if depth > DEPTH:
            raise ValueError(f"kept part: its values nest past {DEPTH} deep")
        data, at = self.data, self.at
        tag = data[at]
        self.at = at + 1
        if tag == _FLOAT:
            self.at = at + 9
            return _F64.unpack_from(data, at + 1)[0]
        if tag == _TUPLE:
            return tuple([self.value(depth + 1) for _ in range(self.count())])
        if tag == _INT:
            self.at = at + 9
            return _I64.unpack_from(data, at + 1)[0]
        if tag == _NONE:
            return None
        if tag == _TRUE:
            return True
        if tag == _FALSE:
            return False
        if tag == _STR:
            return str(self.take(self.u32()), "utf-8", "surrogatepass")
        if tag == _BYTES:
            return self.take(_U64.unpack(self.take(8))[0])
        if tag == _REF:
            ref = self.u32()
            if ref >= len(self.memo):
                raise ValueError(f"kept part: no value {ref} before it")
            return self.memo[ref]
        if tag in (_NUMBERS, _WIDE, _DICTS, _OBJECTS):
            return self.run(tag, depth)
        if tag == _LIST:
            out = []
            self.memo.append(out)
            out += [self.value(depth + 1) for _ in range(self.count())]
            return out
        if tag == _DICT:
            out = {}
            self.memo.append(out)
            keys, values = self.value(depth + 1), self.value(depth + 1)
            if type(keys) is not tuple or type(values) is not tuple or len(keys) != len(values):
                raise ValueError("kept part: a dict's keys aren't its values'")
            out.update(zip(keys, values))
            return out
        if tag == _FROZEN or tag == _SET:
            out = None if tag == _FROZEN else set()
            if out is not None:
                self.memo.append(out)
            items = self.value(depth + 1)
            if type(items) is not tuple:
                raise ValueError("kept part: a set's items aren't a tuple")
            if out is None:
                return frozenset(items)
            out.update(items)
            return out
        if tag == _PICKLE:
            from azurkit.tools.characters.parts import Pickled
            return Pickled(pickle.dumps(self.value(depth + 1), pickle.HIGHEST_PROTOCOL))
        if tag == _BIG:
            return int.from_bytes(self.take(self.u32()), "little", signed=True)
        if tag == _BARRAY:
            out = bytearray(self.take(_U64.unpack(self.take(8))[0]))
            self.memo.append(out)
            return out
        if tag == _ARRAY:
            code = chr(self.take(1)[0])
            if code not in ARRAYS:
                raise ValueError(f"kept part: no codec for an array of {code!r}")
            raw, out = self.take(_U64.unpack(self.take(8))[0]), array(code)
            if len(raw) % out.itemsize:
                raise ValueError(f"kept part: an array of {code!r} {len(raw)} bytes long")
            out.frombytes(raw)
            self.memo.append(out)
            return out
        if tag == _NDARRAY or tag == _NUMBER:
            import numpy as np

            dtype = np.dtype(_named(self.take(self.u32())))
            if tag == _NUMBER:
                return np.frombuffer(self.take(dtype.itemsize), dtype)[0]
            shape = tuple(_U64.unpack(self.take(8))[0] for _ in range(self.take(1)[0]))
            size = dtype.itemsize
            for d in shape:
                size *= d
            out = np.frombuffer(self.take(size), dtype).reshape(shape).copy()
            self.memo.append(out)
            return out
        if tag == _OBJECT:
            cls, names = self.cls()
            if cls.__dataclass_params__.frozen:
                return _made(cls, names, [self.value(depth + 1) for _ in names])
            obj = object.__new__(cls)
            self.memo.append(obj)
            return _made(cls, names, [self.value(depth + 1) for _ in names], obj)
        raise ValueError(f"kept part: no value tagged {tag}")


def _named(raw: bytes) -> str:
    name = raw.decode("ascii", "replace")
    if len(name) < 2 or name[0] not in "<|" or name[1] not in "biufc":
        raise ValueError(f"kept part: no codec for a numpy {name} array")
    return name


def _class(module: object, name: object, fields: object) -> tuple[type, list[str]]:
    """The class a part's head names and its fields, refused by name where
    it isn't one a part may hold or its fields aren't these (a stale part)."""
    if not (isinstance(module, str) and isinstance(name, str) and isinstance(fields, list)):
        raise ValueError("kept part: a head's class isn't [module, name, fields]")
    if module not in MODULES:
        raise ValueError(f"kept part: no codec for a {module}.{name}")
    cls = importlib.import_module(module)
    for part in name.split("."):
        cls = getattr(cls, part, None)
    if not isinstance(cls, type) or not dataclasses.is_dataclass(cls) or cls.__module__ != module:
        raise ValueError(f"kept part: no codec for a {module}.{name}")
    if [f.name for f in dataclasses.fields(cls)] != fields:
        raise ValueError(f"kept part: a {name}'s fields changed since it was kept (a stale part)")
    return cls, fields


def decode(blob: bytes) -> object:
    """The part :func:`encode` kept in ``blob``; ``ValueError`` names what
    isn't so (nothing of it is used)."""
    from compression import zstd

    if not _LITTLE:
        raise ValueError("kept part: only a little-endian host reads parts")
    if bytes(blob[:len(MAGIC)]) != MAGIC or len(blob) < len(MAGIC) + 8:
        raise ValueError("kept part: not one AzurKit keeps")
    size = _U64.unpack_from(blob, len(MAGIC))[0]
    if size > MOST:
        raise ValueError(f"kept part: inflates to {size:,} bytes, past the {MOST:,} a part may hold")
    inflate = zstd.ZstdDecompressor()
    try:
        data = inflate.decompress(memoryview(blob)[len(MAGIC) + 8:], max_length=size)
    except zstd.ZstdError as exc:
        raise ValueError(f"kept part: its bytes don't inflate ({exc})") from None
    if len(data) != size or not inflate.eof or inflate.unused_data:
        raise ValueError(f"kept part: it inflates to other than the {size:,} bytes it lists")
    try:
        n = _U32.unpack_from(data)[0]
        if 4 + n > size:
            raise ValueError("kept part: its head ends early")
        head = json.loads(data[4:4 + n])
        if head["format"] != FORMAT:
            raise ValueError(f"kept part: format {head['format']!r}, not this AzurKit's {FORMAT} (a stale part)")
        reader = _Reader(data, [_class(*c) for c in head["classes"]])
        reader.at = 4 + n
        part = reader.value(0)
    except (KeyError, TypeError, IndexError, UnicodeDecodeError, struct.error, RecursionError) as exc:
        raise ValueError(f"kept part: not one AzurKit reads ({type(exc).__name__})") from None
    if reader.at != len(data):
        raise ValueError(f"kept part: {len(data) - reader.at:,} bytes past its last value")
    return part


__all__ = ["ARRAYS", "DEPTH", "FORMAT", "LEVEL", "MAGIC", "MODULES", "MOST", "decode", "digest", "encode"]

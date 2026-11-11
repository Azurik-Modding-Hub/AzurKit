"""The compiled kernels (D1009) and their Python twins.

Each kernel is C99 in ``native/`` at the repository's root, built by the
dev-only ``nativekit`` with the pinned zig into one library a platform,
committed in ``_native/`` beside this file (macOS arm64 and x86_64, Linux
x86_64 and aarch64 on glibc, Windows x86_64, and a wasm32 side module the
site's Pyodide loads), so neither the release build nor a player needs a
compiler. :func:`library` loads this platform's with ctypes. Each kernel
keeps its Python twin, the reference: the twin runs when the library isn't
there (another platform, a load that fails), when it can't hold a call's
numbers, and whenever ``AZURKIT_NATIVE=0``; both give the same answer, bit
for bit (``tests/test_native.py``). :data:`CALLS` counts the calls each path
answered, and :func:`report` shows them, so a twin that answered beside a
loaded library is seen (the perf gate's native assert).

The first kernel is the randomizer's reach (:func:`solve`): the solver's
least fixpoint (``planner/solver.py``'s ``Logic._solve``) over
:class:`Tables`, its graphs and rules as integer ids. The second is the
fill's (:func:`attempt`, :func:`accept`): a whole attempt of
``planner/fill.py``'s fill and a shaped candidate's need and play, on the
blob ``fill._Kernel`` packs, its twins those modules' own.
"""

from __future__ import annotations

import collections
import ctypes
import hashlib
import itertools
import operator
import os
import platform
import sys
from array import array
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ABI = 2                                   # native/reach.c's ABI: a library of another one isn't loaded
MAGIC = 0x314843524b5a                    # its tables' first word
FOLDER = Path(__file__).with_name("_native")
TARGETS = {                               # (sys.platform, machine) -> the library nativekit builds for it
    ("darwin", "aarch64"): "macos-arm64.dylib",
    ("darwin", "x86_64"): "macos-x86_64.dylib",
    ("linux", "x86_64"): "linux-x86_64.so",    # glibc 2.17 and later
    ("linux", "aarch64"): "linux-aarch64.so",
    ("win32", "x86_64"): "windows-x86_64.dll",
    ("emscripten", "wasm32"): "emscripten-wasm32.so",   # a side module Pyodide's ctypes loads
}
KERNELS = ("reach", "attempt", "origins", "linear", "chain", "boxes", "sample", "heights", "skinned", "signed", "runs",
           "ray", "rays", "decimate", "thin", "smooth", "dxt", "atan2", "raster", "spring", "clear")
DEPTH = 200                               # the deepest rule the kernel evaluates (its recursion); deeper: the twin
LIMIT = 1 << 62                           # every number the kernel holds stays under it (int64); else the twin
                                          # (no number is refused for its size, D23)

CALLS: collections.Counter = collections.Counter()   # the calls this process answered, by path ("kernel", "twin"),
#                                                      and those its engine's process handed it (:func:`taken`)

_OPS = {"false": 0, "true": 1, "counter": 2, "flag": 3, "sum": 4, "and": 5, "or": 6}
_H, _G = 20, 11                           # the tables' header words and a graph's (reach.c's H_* and G_*)


def target() -> str | None:
    """This platform's library name, or None where none is built (musl, Windows on arm)."""
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    if sys.platform == "linux":
        try:
            if not (os.confstr("CS_GNU_LIBC_VERSION") or "").startswith("glibc"):
                return None
        except (ValueError, OSError):
            return None
    return TARGETS.get((sys.platform, machine))


def _load() -> tuple[ctypes.CDLL | None, str, str | None]:
    """(the library or None, its name or why there is none, its sha256[:12])."""
    if os.environ.get("AZURKIT_NATIVE", "1") == "0":
        return None, "AZURKIT_NATIVE=0", None
    name = target()
    if name is None:
        return None, f"no library for {sys.platform} {platform.machine()}", None
    path = FOLDER / name
    try:
        sha12 = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
        lib = ctypes.CDLL(str(path))
        lib.az_abi.restype = ctypes.c_int64
        if lib.az_abi() != ABI:
            return None, f"{name} is ABI {lib.az_abi()}, not {ABI}", sha12
    except (OSError, AttributeError) as e:
        return None, f"{name} doesn't load: {e}", None
    p64, pu64 = ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_uint64)
    lib.az_reach_need.argtypes, lib.az_reach_need.restype = [p64, p64], ctypes.c_int64
    lib.az_reach.argtypes = [p64, p64, p64, p64, pu64, pu64, pu64, p64, *[pu64] * 6, p64, p64, pu64, pu64, p64,
                             pu64, p64]
    lib.az_reach.restype = ctypes.c_int64
    vp, i64, f64 = ctypes.c_void_p, ctypes.c_int64, ctypes.c_double
    try:
        for fn, args in (("az_attempt_need", [vp] * 6), ("az_attempt", [vp] * 8), ("az_accept", [vp] * 9),
                         ("az_origins", [vp, vp, i64, vp, i64, vp, vp, i64, vp, vp]),
                         ("az_linear", [vp, vp, vp, vp, vp, i64, vp]),
                         ("az_chain", [vp, vp, vp, i64, vp, vp, vp, i64, f64, f64, vp]),
                         ("az_boxes", [vp, i64, f64, vp]),
                         ("az_sample", [vp, i64, vp, i64, vp, vp, i64, vp, vp]),
                         ("az_heights", [vp, vp, i64, vp, vp, i64, vp, vp]),
                         ("az_skinned", [vp, vp, vp, i64, vp, vp, i64, i64, vp]),
                         ("az_signed", [vp, i64, vp, vp, i64, f64, f64, vp, vp, vp]),
                         ("az_ray", [vp, f64, f64, f64, i64, f64, f64, f64, vp]),
                         ("az_rays", [vp, i64, vp, i64, f64, f64, f64, vp, vp]),
                         ("az_decimate_need", [i64] * 4),
                         ("az_decimate", [i64, vp, vp, i64, vp, vp, vp, vp, vp, ctypes.c_char_p, i64, vp, vp, vp,
                                          ctypes.c_char_p, vp, vp, i64, f64, i64, f64, vp, i64, i64, i64]),
                         ("az_runs", [ctypes.c_char_p, i64, ctypes.c_char_p, i64, vp, i64]),
                         ("az_thin", [vp, i64, f64, f64, vp, vp]), ("az_smooth", [vp, i64, i64, vp, i64, vp]),
                         ("az_dxt", [ctypes.c_char_p, i64, i64, i64, vp]), ("az_atan2", [vp, vp, i64, vp]),
                         ("az_raster", [vp, i64, i64, vp, vp]),
                         ("az_spring", [vp, vp, i64, i64, i64, vp, vp, i64, f64, i64, i64, i64, vp, vp, vp]),
                         ("az_clear_need", [vp, vp]), ("az_clear", [vp] * 21)):
            getattr(lib, fn).argtypes, getattr(lib, fn).restype = args, i64
    except AttributeError as e:
        return None, f"{name} doesn't load: {e}", None
    return lib, name, sha12


_LIB: tuple | None = None


def library() -> ctypes.CDLL | None:
    """This platform's loaded library, once a process; None runs the twins."""
    global _LIB
    if _LIB is None:
        _LIB = _load()
    return _LIB[0]


def report() -> dict:
    """What a host reports of the kernels: ``{"loaded", "library", "sha12",
    "kernels", "why", "calls"}`` (``why``: the reason the twins run, else
    None; ``calls``: :data:`CALLS`, ``{"kernel", "twin"}``)."""
    library()
    lib, name, sha12 = _LIB
    return {"loaded": lib is not None, "library": name if lib else None, "sha12": sha12,
            "kernels": list(KERNELS) if lib else [], "why": None if lib else name,
            "calls": {"kernel": CALLS["kernel"], "twin": CALLS["twin"]}}


def taken() -> dict[str, int]:
    """:data:`CALLS` since the last time, emptied, for a host's engine to hand
    to what reports them (an app's engine process, a site's worker: each may
    end before anyone asks). A count another thread adds beside it may be
    handed twice, never lost: only none or some is read."""
    return {path: n for path in ("kernel", "twin") if (n := CALLS.pop(path, 0))}


# ---- the reach -------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Graph:
    """One option set's compiled graph over :class:`Tables`' ids: each
    node's edges ``((to, rule), ...)``, the credits ``(flag, node,
    terminal, rule)``, the locations ``(location, node, rule)``, the disc
    teleports ``(from, to, rule, the disc's guardian slot)`` and the
    victory rule (``solver._Rules``' ``adj``, ``credits``, ``locations``,
    ``teleports`` and ``victory``)."""
    adj: tuple[tuple[tuple[int, int], ...], ...]
    credits: tuple[tuple[int, int, bool, int], ...] = ()
    locations: tuple[tuple[int, int, int], ...] = ()
    teleports: tuple[tuple[int, int, int, int], ...] = ()
    victory: int = 0


@dataclass(eq=False)
class Tables:
    """A database's logic as the reach reads it, every name an id: ``nodes``
    canonical nodes numbered in the solver's sorted order (an escape tries
    them in it), ``flags``, ``locations`` and ``counters`` counted; the
    ``start`` node; ``rules``, each a tuple whose children (of ``and`` and
    ``or``) are earlier rules: ``("false",)``, ``("true",)``,
    ``("counter", c, n)`` (counter c >= n), ``("flag", f)``, ``("sum", n,
    (c, ...))`` (the counters' sum >= n: a key lock's worst case with its
    refund keys) or ``("and" | "or", (rule, ...))``; each item's ``(counter,
    increment)`` pairs, the ``discs`` (counters an item adds to at its first
    copy only), each location's vanilla yield and refund key ``(key counter,
    pending counter)`` or ``(-1, -1)``, each node's flags forced on entry in
    logic and physically, each no-return region ``(its guardian slot,
    nodes)`` and the option sets' :class:`Graph` s. Checked and packed for
    the kernel as it is made: a ``ValueError`` names what is wrong."""
    nodes: int
    flags: int
    locations: int
    counters: int
    start: int
    rules: tuple[tuple, ...]
    items: tuple[tuple[tuple[int, int], ...], ...]
    discs: frozenset[int]
    yields: tuple[int, ...]
    refund: tuple[tuple[int, int], ...]
    forced: tuple[tuple[int, ...], ...]
    forced_phys: tuple[tuple[int, ...], ...]
    regions: tuple[tuple[int, tuple[int, ...]], ...]
    graphs: tuple[Graph, ...]
    blob: array = field(init=False, repr=False)
    twin_only: bool = field(init=False, repr=False)  # a rule deeper than DEPTH or a number past LIMIT: the twin
    _view: object = field(init=False, repr=False, default=None)
    _twin: tuple | None = field(init=False, repr=False, default=None)
    _limits: tuple | None = field(init=False, repr=False, default=None)

    def __post_init__(self):
        self.blob, self.twin_only = _pack(self)

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k not in ("_view", "_twin", "_limits")}

    def __setstate__(self, state):
        self.__dict__.update(state, _view=None, _twin=None, _limits=None)


@dataclass(frozen=True)
class Solved:
    """:func:`solve`'s answer (``Logic._solve``'s, as ids): the nodes
    ``reached`` in logic, the ``safe`` ones, ``phys`` (R_phys), the
    ``traps``, those ``after`` completion, the locations ``got``, the
    ``flags``, ``victory`` and the trick-free traps (``free``); the
    ``counters`` and items ``held`` at the end; the ``rounds`` run, each
    location's and flag's round (-1: before the first) and, with ``log``,
    each round's traps found and trick-free ones."""
    reached: frozenset[int]
    safe: frozenset[int]
    phys: frozenset[int]
    traps: frozenset[int]
    after: frozenset[int]
    got: frozenset[int]
    flags: frozenset[int]
    victory: bool
    free: frozenset[int]
    counters: tuple[int, ...]
    held: tuple[int, ...]
    rounds: int
    loc_round: tuple[int, ...]
    flag_round: tuple[int, ...]
    found_log: tuple[frozenset[int], ...] = ()
    walked_log: tuple[frozenset[int], ...] = ()


def _int(x, what: str, big: list) -> int:
    """``x``, an integer, as a word: 0 in its place (and ``big`` marked) past LIMIT, where the twin runs."""
    if type(x) is not int:
        raise ValueError(f"{what}: {x!r} is no integer")
    if -LIMIT < x < LIMIT:
        return x
    big.append(what)
    return 0


def _id(x, n: int, what: str) -> int:
    if type(x) is not int or not 0 <= x < n:
        raise ValueError(f"{what}: {x!r} is no id below {n}")
    return x


def _pack(t: Tables) -> tuple[array, bool]:
    """``t`` checked, as reach.c's words, and whether only the twin can run it."""
    n, f, nl, nc, ni = t.nodes, t.flags, t.locations, t.counters, len(t.items)
    for what, v in (("nodes", n), ("flags", f), ("locations", nl), ("counters", nc)):
        if type(v) is not int or v < 0:
            raise ValueError(f"{what}: {v!r} is no count")
    _id(t.start, n, "start")
    words = [0] * _H
    pos, depth, big = [], [], []
    for i, r in enumerate(t.rules):
        op = r[0] if isinstance(r, tuple) and r else None
        if op not in _OPS:
            raise ValueError(f"rule {i}: {r!r} isn't a rule")
        pos.append(len(words))
        if op in ("false", "true"):
            words.append(_OPS[op])
            depth.append(1)
        elif op == "counter":
            words += [2, _id(r[1], nc, f"rule {i}'s counter"), _int(r[2], f"rule {i}'s threshold", big)]
            depth.append(1)
        elif op == "flag":
            words += [3, _id(r[1], f, f"rule {i}'s flag")]
            depth.append(1)
        elif op == "sum":
            terms = [_id(c, nc, f"rule {i}'s counter") for c in r[2]]
            words += [4, _int(r[1], f"rule {i}'s threshold", big), len(terms), *terms]
            depth.append(1)
        else:
            kids = [_id(k, i, f"rule {i}'s child (an earlier rule)") for k in r[1]]
            words += [_OPS[op], len(kids), *(pos[k] for k in kids)]
            depth.append(1 + max((depth[k] for k in kids), default=0))

    def rule(x, what):
        return pos[_id(x, len(pos), what)]
    words[11] = len(words)                            # H_ITEMS: I + 1 offsets, then (counter, increment) pairs
    offsets = len(words)
    words += [0] * (ni + 1)
    for i, pairs in enumerate(t.items):
        words[offsets + i] = len(words)
        if len({c for c, _ in pairs}) != len(pairs):
            raise ValueError(f"item {i}: a counter twice")
        for c, inc in pairs:
            words += [_id(c, nc, f"item {i}'s counter"), _int(inc, f"item {i}'s increment", big)]
    words[offsets + ni] = len(words)
    words[12] = len(words)                            # H_DISC
    words += [int(c in t.discs) for c in range(nc)]
    if any(type(c) is not int or not 0 <= c < nc for c in t.discs):
        raise ValueError(f"discs: {sorted(t.discs)} name a counter that isn't")
    for what, rows in (("yields", t.yields), ("refund", t.refund)):
        if len(rows) != nl:
            raise ValueError(f"{what}: {len(rows)} rows for {nl} locations")
    words[13] = len(words)                            # H_YIELD
    words += [_int(y, f"location {loc}'s yield", big) for loc, y in enumerate(t.yields)]
    words[14] = len(words)                            # H_REFUND
    for loc, (key, pend) in enumerate(t.refund):
        if (key, pend) != (-1, -1):
            _id(key, nc, f"location {loc}'s refund key"), _id(pend, nc, f"location {loc}'s pending counter")
        words += [key, pend]

    def csr(rows, check):
        """N + 1 offsets, then each row's words."""
        at = len(words)
        words.extend([0] * (len(rows) + 1))
        for u, row in enumerate(rows):
            words[at + u] = len(words)
            for x in row:
                words.extend(check(u, x))
        words[at + len(rows)] = len(words)
        return at
    for slot, (what, rows) in ((15, ("forced", t.forced)), (16, ("forced_phys", t.forced_phys))):
        if len(rows) != n:
            raise ValueError(f"{what}: {len(rows)} rows for {n} nodes")
        words[slot] = csr(rows, lambda u, x, what=what: [_id(x, f, f"node {u}'s {what} flag")])
    words[17] = len(words)                            # H_REGIONS: R, R slots, R + 1 offsets, nodes
    words += [len(t.regions), *(_id(s, nl, "a region's slot") for s, _ in t.regions)]
    csr([nodes for _, nodes in t.regions], lambda u, x: [_id(x, n, f"region {u}'s node")])
    words[18] = len(words)                            # H_GRAPHS
    at = len(words)
    words += [0] * len(t.graphs)
    kmax = mmax = 0
    for gi, g in enumerate(t.graphs):
        if len(g.adj) != n:
            raise ValueError(f"graph {gi}: {len(g.adj)} adjacency rows for {n} nodes")
        head = len(words)
        words[at + gi] = head
        words += [0] * _G
        radj = [[] for _ in range(n)]
        for u, row in enumerate(g.adj):
            for v, r in row:
                radj[_id(v, n, f"graph {gi}'s edge from {u}")].append((u, r))
        words[head] = csr(g.adj, lambda u, e, gi=gi: [e[0], rule(e[1], f"graph {gi}'s edge rule")])
        words[head + 1] = csr(radj, lambda u, e, gi=gi: [e[0], rule(e[1], f"graph {gi}'s edge rule")])
        words[head + 2], words[head + 3] = len(g.credits), len(words)
        by_node = [[] for _ in range(n)]
        for j, (fl, node, terminal, r) in enumerate(g.credits):
            words += [_id(fl, f, f"graph {gi}'s credit flag"), _id(node, n, f"graph {gi}'s credit node"),
                      int(bool(terminal)), rule(r, f"graph {gi}'s credit rule")]
            by_node[node].append(j)
        words[head + 4] = csr(by_node, lambda u, j: [j])
        words[head + 5], words[head + 6] = len(g.locations), len(words)
        for loc, node, r in g.locations:
            words += [_id(loc, nl, f"graph {gi}'s location"), _id(node, n, f"graph {gi}'s location node"),
                      rule(r, f"graph {gi}'s location rule")]
        words[head + 7], words[head + 8] = len(g.teleports), len(words)
        for a, b, r, slot in g.teleports:
            words += [_id(a, n, f"graph {gi}'s teleport"), _id(b, n, f"graph {gi}'s teleport"),
                      rule(r, f"graph {gi}'s teleport rule"), _id(slot, nl, f"graph {gi}'s teleport slot")]
        words[head + 9] = rule(g.victory, f"graph {gi}'s victory")
        at_node = [[] for _ in range(n)]
        for j, (_, node, _) in enumerate(g.locations):
            at_node[node].append(j)
        words[head + 10] = csr(at_node, lambda u, j: [j])   # G_LBN: each node's location rows
        kmax, mmax = max(kmax, len(g.credits)), max(mmax, len(g.locations))
    words[:11] = [MAGIC, ABI, n, f, nl, nc, ni, t.start, len(t.graphs), kmax, mmax]
    words[19] = int(_monotone(t))                     # H_MONO
    return array("q", words), bool(big) or max(depth, default=0) > DEPTH


def _monotone(t: Tables) -> bool:
    """Whether no take can make a rule false (reach.c's ``H_MONO``): no
    increment or yield below 0, and each refund key's pending counter, which
    its take lowers by one, read only in sums holding the key (which that
    take raises by at least one: no disc, a yield of at least one) as often."""
    if any(inc < 0 for item in t.items for _, inc in item) or any(y < 0 for y in t.yields):
        return False
    keys = collections.defaultdict(set)
    for loc, (key, pend) in enumerate(t.refund):
        if key >= 0:
            if key in t.discs or key == pend or t.yields[loc] < 1:
                return False
            keys[pend].add(key)
    for r in t.rules:
        if r[0] == "counter" and r[1] in keys:
            return False
        if r[0] == "sum" and keys.keys() & set(r[2]):
            terms = collections.Counter(r[2])
            if any(terms[key] < terms[pend] for pend in keys.keys() & terms.keys() for key in keys[pend]):
                return False
    return True


def _twin_rules(t: Tables) -> tuple:
    """The twin's rules as closures over (counters, flags), each item's
    increments and the forced flags as sets."""
    fns = []
    for r in t.rules:
        op = r[0]
        if op in ("false", "true"):
            fn = (lambda c, f: True) if op == "true" else (lambda c, f: False)
        elif op == "counter":
            fn = (lambda i, k: lambda c, f: c[i] >= k)(r[1], r[2])
        elif op == "flag":
            fn = (lambda i: lambda c, f: i in f)(r[1])
        elif op == "sum":
            fn = (lambda k, terms: lambda c, f: sum(c[i] for i in terms) >= k)(r[1], tuple(r[2]))
        else:
            kids = tuple(fns[k] for k in r[1])
            fn = ((lambda kids: lambda c, f: all(k(c, f) for k in kids)) if op == "and" else
                  (lambda kids: lambda c, f: any(k(c, f) for k in kids)))(kids)
        fns.append(fn)
    radj = []
    for g in t.graphs:
        rows = [[] for _ in range(t.nodes)]
        for u, row in enumerate(g.adj):
            for v, r in row:
                rows[v].append((u, r))
        radj.append(rows)
    return (fns, [dict(pairs) for pairs in t.items], [frozenset(x) for x in t.forced],
            [frozenset(x) for x in t.forced_phys], radj)


def _twin(t: Tables, graph: int, phys: int, free: int, counters: Sequence[int], held: Sequence[int],
          flags: Iterable[int], gives: Sequence[int], got: Iterable[int] | None, late: Iterable[int], traps: bool,
          log: bool, take_got: bool = False) -> Solved:
    """The reach in Python (the reference): ``Logic._solve``, line for line, over ids."""
    if t._twin is None:
        t._twin = _twin_rules(t)
    ev, incs, forced, forced_phys, radjs = t._twin
    lg, pg, fg = t.graphs[graph], t.graphs[phys], t.graphs[free]
    c, h = list(counters), list(held)
    base, flags = frozenset(flags), set(flags)
    collected = got is not None
    got, late = set(got or ()), frozenset(late)
    start = t.start

    def take(h, c, loc):
        if (name := gives[loc]) < 0:
            return
        n = t.yields[loc]
        first = h[name] == 0
        h[name] += n
        for cn, inc in t.items[name]:
            c[cn] += inc * first if cn in t.discs else inc * n
        key, pend = t.refund[loc]
        if incs[name].get(key, 0) > 0 and c[pend] > 0:
            c[pend] -= 1

    def bfs(adj, sources, c, f):
        seen, todo = set(sources), collections.deque(sources)
        while todo:
            for v, r in adj[todo.popleft()]:
                if v not in seen and ev[r](c, f):
                    seen.add(v)
                    todo.append(v)
        return seen

    def closure(g, f):
        f = set(f)
        while True:
            seen = bfs(g.adj, [start], c, f)
            new = [fl for fl, node, _, r in g.credits if fl not in f and node in seen and ev[r](c, f)]
            if not new:
                return seen, f
            f.update(new)

    def returners(g, radj):
        local = collections.defaultdict(set)
        for fl, node, _, r in g.credits:
            if fl not in base and ev[r](c, base):
                local[node].add(fl)
        at = {node: base | fs for node, fs in local.items()}
        seen, todo = {start}, collections.deque([start])
        while todo:
            for u, r in radj[todo.popleft()]:
                if u not in seen and ev[r](c, at.get(u, base)):
                    seen.add(u)
                    todo.append(u)
        return seen

    def escape(g, node, f0):
        ec, eh, f, took = list(c), list(h), set(f0), set(got)
        sources = [node]
        while True:
            seen = bfs(g.adj, sources, ec, f)
            if start in seen:
                return True, seen, f
            jumps = [b for a, b, r, slot in g.teleports if a in seen and b not in seen and slot not in got
                     and ev[r](ec, f)]
            locs = [loc for loc, n, r in g.locations if loc not in took and n in seen and ev[r](ec, f)]
            new = [fl for fl, n, _, r in g.credits if fl not in f and n in seen and ev[r](ec, f)]
            if not (jumps or locs or new):
                return False, seen, f
            sources += jumps
            for loc in locs:
                took.add(loc)
                take(eh, ec, loc)
            f.update(new)

    def escaping(gi, nodes, forced, credited):
        if not nodes:
            return set()
        g = t.graphs[gi]
        home = returners(g, radjs[gi])
        out, dead = nodes & home, set()
        for n in sorted(nodes - home):
            if n in dead:
                continue
            ok, seen, f = escape(g, n, base | (forced[n] & credited))
            if ok:
                out.add(n)
            else:
                dead.update(m for m in seen if forced[m] & credited <= f)
        return out

    safe = {start}
    if take_got:   # Logic.reach's collected: their items held first
        for loc in sorted(got):
            take(h, c, loc)
    for loc, (key, pend) in enumerate(t.refund):     # Logic._pending
        if key >= 0 and loc not in got and (name := gives[loc]) >= 0 and incs[name].get(key, 0) > 0:
            c[pend] = max(c[pend], 1)
    got -= late
    now, trapped, freed = set(), set(), set()
    loc_round, flag_round = [-1] * t.locations, [-1] * t.flags
    found_log, walked_log = [], []
    rnd = 0
    while True:
        reached = bfs(lg.adj, [start], c, flags)
        safe |= escaping(graph, reached - safe, forced, flags)
        ph, settable = closure(pg, flags) if traps else (set(), set())
        maybe = ph - safe
        found = maybe - escaping(phys, maybe, forced_phys, settable)
        walked = found if free == phys or not found else found & closure(fg, flags)[0]
        trapped |= found
        freed |= walked
        if log:
            found_log.append(frozenset(found))
            walked_log.append(frozenset(walked))
        locs = [loc for loc, n, r in lg.locations if loc not in got and loc not in now and n in safe
                and ev[r](c, flags)]
        new = [fl for fl, n, terminal, r in lg.credits if fl not in flags
               and (n in safe or terminal and n in reached) and ev[r](c, flags)]
        if not (locs or new):
            got |= late
            after = {n for slot, nodes in t.regions if slot in got for n in nodes if n in ph}
            return Solved(frozenset(reached), frozenset(safe), frozenset(ph), frozenset(trapped), frozenset(after),
                          frozenset(got | now), frozenset(flags), bool(ev[lg.victory](c, flags)), frozenset(freed),
                          tuple(c), tuple(h), rnd + 1, tuple(loc_round), tuple(flag_round), tuple(found_log),
                          tuple(walked_log))
        for loc in locs:
            loc_round[loc] = rnd
            if collected:
                if loc in late:
                    got.add(loc)
                now.add(loc)
            else:
                got.add(loc)
                take(h, c, loc)
        for fl in new:
            flag_round[fl] = rnd
        flags.update(new)
        rnd += 1


def _words(ids: Iterable[int], count: int):
    out = [0] * max(1, (count + 63) // 64)
    for i in ids:
        out[i >> 6] |= 1 << (i & 63)
    return (ctypes.c_uint64 * len(out))(*out)


_DECODED: dict[bytes, frozenset[int]] = {}   # a set's words to its ids: a fill's reaches read a few hundred sets, over and over
_DECODED_KEPT = 1024
_BITS = tuple(bytes((b >> i) & 1 for i in range(8)) for b in range(256))   # a byte's bits, the lowest first, as 0 or 1


def _ids(words, count: int) -> frozenset[int]:
    raw = bytes(words)[:8 * ((count + 63) // 64)]
    if (got := _DECODED.get(raw)) is not None:
        return got
    if sys.byteorder == "little":   # bit i is byte i // 8's bit i % 8: the ids picked at C speed
        got = frozenset(itertools.compress(range(8 * len(raw)), b"".join(map(_BITS.__getitem__, raw))))
    else:
        out = []
        for w in range((count + 63) // 64):
            x = words[w]
            while x:
                low = x & -x
                out.append(w * 64 + low.bit_length() - 1)
                x ^= low
        got = frozenset(out)
    if len(_DECODED) >= _DECODED_KEPT:
        _DECODED.clear()
    _DECODED[raw] = got
    return got


def _ids_below(ids: Iterable[int], n: int, what: str) -> list[int]:
    """``ids`` as a list, each an id below ``n`` (:func:`_id`'s, at a whole set's C speed)."""
    out = list(ids)
    if out and (set(map(type, out)) != {int} or min(out) < 0 or max(out) >= n):
        for x in out:
            _id(x, n, what)
    return out


def _limits(t: Tables) -> tuple:
    """What :func:`solve` reads of ``t`` to prove a call's numbers fit the kernel: a sum rule's most terms; each item's
    largest increment, with a 0 last for an empty location's -1; each location's yield, sized; their sum; the largest
    increment."""
    if t._limits is None:
        yields = tuple(map(abs, t.yields))
        largest = (*(max([abs(inc) for _, inc in item] + [0]) for item in t.items), 0)
        t._limits = (max([len(r[2]) for r in t.rules if r[0] == "sum"] + [1]), largest, yields, sum(yields),
                     max(largest))
    return t._limits


def _row(a: array):
    """An array of int64 as the kernel's pointer to its words."""
    return (ctypes.c_int64 * len(a)).from_buffer(a)


def _native(lib, t: Tables, graph: int, phys: int, free: int, counters: Sequence[int], held: Sequence[int],
            flags: Iterable[int], gives: Sequence[int], got: Iterable[int] | None, late: Iterable[int], traps: bool,
            log: bool, take_got: bool = False) -> Solved:
    """The reach in reach.c."""
    i64, u64 = ctypes.c_int64, ctypes.c_uint64
    if t._view is None:
        view = (i64 * len(t.blob)).from_buffer(t.blob)
        ints = (i64 * 1)()
        t._view = (view, lib.az_reach_need(view, ints), ints[0])
    view, wbn, win = t._view
    n, nl, nf, nw = t.nodes, t.locations, t.flags, max(1, (t.nodes + 63) // 64)
    cap = nl + nf + 2 if log else 0
    call = (i64 * 7)(graph, phys, free, int(got is not None), int(bool(traps)), cap,
                     int(bool(take_got) and got is not None))
    # the long rows as arrays (their ints packed at C speed), each the kernel's through its buffer
    c, h, gv = array("q", counters or (0,)), array("q", held or (0,)), array("q", gives or (0,))
    loc_round, flag_round = array("q", bytes(8 * max(1, nl))), array("q", bytes(8 * max(1, nf)))
    fl, gt, lt = _words(flags, nf), _words(got or (), nl), _words(late, nl)
    reached, safe, ph, traps_, after, freed = ((u64 * nw)() for _ in range(6))
    found_log, walked_log = (u64 * max(1, cap * nw))(), (u64 * max(1, cap * nw))()
    out = (i64 * 2)()
    rc = lib.az_reach(view, call, *(_row(a) for a in (c, h)), fl, gt, lt, _row(gv), reached, safe, ph, traps_, after,
                      freed, _row(loc_round), _row(flag_round), found_log, walked_log, out, (u64 * wbn)(), (i64 * win)())
    if rc:
        raise RuntimeError(f"reach.c refused the call ({rc}): the tables aren't its ABI {ABI}'s or the log overflowed")
    rounds = out[0]
    logs = [tuple(_ids((u64 * nw).from_buffer(buf, 8 * nw * k), n) for k in range(rounds)) if log else ()
            for buf in (found_log, walked_log)]
    return Solved(_ids(reached, n), _ids(safe, n), _ids(ph, n), _ids(traps_, n), _ids(after, n), _ids(gt, nl),
                  _ids(fl, nf), bool(out[1]), _ids(freed, n), tuple(c[:t.counters]), tuple(h[:len(t.items)]),
                  rounds, tuple(loc_round[:nl]), tuple(flag_round[:nf]), *logs)


def solve(t: Tables, graph: int, phys: int, free: int, *, counters: Sequence[int], held: Sequence[int],
          flags: Iterable[int], gives: Sequence[int], got: Iterable[int] | None = None, late: Iterable[int] = (),
          traps: bool = True, log: bool = False, take_got: bool = False) -> Solved:
    """``Logic._solve``'s fixpoint on ``t``: the logic graph ``graph``, the
    physical ``phys`` and the trick-free physical ``free`` (``phys`` again
    when the options turn no skip on), from ``counters`` and the items
    ``held`` (``t.items``' order), the ``flags`` credited from the start,
    each location's item ``gives`` (-1: none), and with ``got`` (the
    tracker's collected locations) and ``late`` (the guardian slots among
    them collected only from the round that reaches them) or not, with
    ``take_got`` each of ``got``'s items taken first (in id order: the counters
    and items held after them, as :meth:`Logic.reach`'s collected); the traps
    only with ``traps``, each round's with ``log``. In reach.c when this
    platform's library is loaded and holds the call's numbers, else in the
    twin: the same answer."""
    nl, ni = t.locations, len(t.items)
    for i in (graph, phys, free):
        _id(i, len(t.graphs), "graph")
    if set(map(type, (*counters, *held))) - {int}:
        raise ValueError("counters and held: each value is an integer")
    if len(counters) != t.counters or len(held) != ni or len(gives) != nl:
        raise ValueError(f"counters, held and gives: {len(counters)}, {len(held)} and {len(gives)} values for "
                         f"{t.counters} counters, {ni} items and {nl} locations")
    flags, late = _ids_below(flags, t.flags, "flag"), _ids_below(late, nl, "late")
    got = None if got is None else _ids_below(got, nl, "got")
    if gives and (set(map(type, gives)) != {int} or min(gives) < -1 or max(gives) >= ni):
        for loc, x in enumerate(gives):
            if type(x) is not int or not -1 <= x < ni:
                raise ValueError(f"gives: location {loc} holds {x!r}, no item id or -1")
    lib = library()
    if lib is not None and not t.twin_only:
        terms, largest, yields, all_yields, most = _limits(t)
        top = max(map(abs, (*counters, *held)), default=0) + all_yields + 1
        if (top + most * all_yields + nl) * terms >= LIMIT:   # past the growth's bound: its sum decides
            top += sum(map(operator.mul, map(largest.__getitem__, gives), yields)) + nl - gives.count(-1)
        if top * terms < LIMIT:
            CALLS["kernel"] += 1
            return _native(lib, t, graph, phys, free, counters, held, flags, gives, got, late, traps, log, take_got)
    CALLS["twin"] += 1
    return _twin(t, graph, phys, free, counters, held, flags, gives, got, late, traps, log, take_got)


# ---- the fill's attempt ----------------------------------------------------------------------------------------------
def attempt(blob: array, tables: Sequence[Tables], call: array, words: int) -> array | int | None:
    """One attempt of the fill in ``native/fill.c`` (its twin, the reference, is ``planner/fill.py``'s
    ``_Slots.attempt``): the fill's packed ``blob``, the reach ``tables`` it reads (the plan's options', then a seed
    difficulty's rungs, four at most) and the ``call``'s words; its answer's ``words`` words, an error's code below 0
    (the call's told log too short, or a kernel that can't: fill.c names them), or None without the library."""
    if (lib := library()) is None:
        return None
    at = [*map(_at, (t.blob for t in tables)), *[None] * (4 - len(tables))]
    need = lib.az_attempt_need(_at(blob), *at, _at(call))
    if need < 0:
        return need
    space, out = array("q", bytes(8 * need)), array("q", bytes(8 * words))
    if rc := lib.az_attempt(_at(blob), *at, _at(call), _at(space), _at(out)):
        return rc
    CALLS["kernel"] += 1
    return out


def accept(blob: array, tables: Sequence[Tables], call: array, placement: array, words: int) -> array | int | None:
    """``native/fill.c``'s az_accept: the seed difficulty's need or play (``planner/difficulty.py``'s, the twins) of a
    candidate ``placement`` on :func:`attempt`'s blob and tables, its answer's ``words`` words; an error's code below
    0, or None without the library."""
    if (lib := library()) is None:
        return None
    at = [*map(_at, (t.blob for t in tables)), *[None] * (4 - len(tables))]
    need = lib.az_attempt_need(_at(blob), *at, _at(call))
    if need < 0:
        return need
    space, out = array("q", bytes(8 * need)), array("q", bytes(8 * words))
    if rc := lib.az_accept(_at(blob), *at, _at(call), _at(placement), _at(space), _at(out)):
        return rc
    CALLS["kernel"] += 1
    return out


# ---- the dress ------------------------------------------------------------------------------------------------------
# tools/characters' clip and skeleton kernels (native/dress.c) over packed buffers: each returns None without the
# library, and its caller then runs its twin (retarget's pose and origins, bake_clip's rows, _sampled's, _runs).
def _at(a: array) -> int | None:
    return a.buffer_info()[0] if len(a) else None


def origins(parent: array, bone: array, index: array, keys: array, times: array, *,
            origin: bool = True) -> tuple[array, array | None] | None:
    """``retarget.pose`` (world rotations, times x bones x 4) and
    ``origins`` (times x bones x 3; ``origin``) at each of ``times``: the
    bones' ``parent`` ids (each below its own) and ``bone``'s 15 doubles a
    bone (jo, rest q, ra, rest t); ``index``, 14 ids a keyed bone (its 7
    components', T then q: an offset and a count into ``keys``, 4 doubles
    a key; 0 keys: the rest value)."""
    if (lib := library()) is None:
        return None
    nb, nt = len(parent), len(times)
    world = array("d", bytes(32 * nb * nt))
    at = array("d", bytes(24 * nb * nt)) if origin else None
    lib.az_origins(_at(parent), _at(bone), nb, _at(index), len(index) // 14, _at(keys), _at(times), nt, _at(world),
                   _at(at) if at is not None else None)
    return world, at


def linear(index: array, keys: array, rest: array, m: array, times: array) -> array | None:
    """``bake_clip``'s rows (times x 12): the 4x4 ``m`` (row-major) times
    the 4 components' values, left and right slopes at each time (``index``:
    an offset and a count a component; 0 keys: ``rest``'s value)."""
    if (lib := library()) is None:
        return None
    rows = array("d", bytes(96 * len(times)))
    lib.az_linear(_at(index), _at(keys), _at(rest), _at(m), _at(times), len(times), _at(rows))
    return rows


def chain(link: array, index: array, keys: array, a: array, c: array, times: array, length: float,
          h: float) -> array | None:
    """``retarget._sampled``'s rows (times x 12: the rotation, its left
    and right slopes over ``h``): ``link``'s 12 doubles a chain bone (jo,
    rest q, ra) and ``index``'s 8 ids (4 components' offset and count)."""
    if (lib := library()) is None:
        return None
    rows = array("d", bytes(96 * len(times)))
    lib.az_chain(_at(link), _at(index), _at(keys), len(link) // 12, _at(a), _at(c), _at(times), len(times),
                 length, h, _at(rows))
    return rows


def boxes(values: array, scale: float) -> array | None:
    """``characters._box`` of each 12 of ``values`` (a damage marker's)
    at ``scale``: its low and high corners' bounds (6 doubles a box)."""
    if (lib := library()) is None:
        return None
    out = array("d", bytes(4 * len(values)))
    lib.az_boxes(_at(values), len(values) // 12, scale, _at(out))
    return out


def sample(bone: array, index: array, keys: array, times: int, nt: int, q: int, t: int) -> bool:
    """``_player_crossfade.sample`` of a rig's ``bone`` values (as
    :func:`origins`') and a clip's ``index`` and ``keys`` (0 keys: the
    rest value; key times finite and in order) at the ``nt`` doubles at
    ``times``, into ``q`` (bones x nt x 4, canon's) and ``t`` (x 3): the
    numpy buffers' addresses, the caller's to keep; False without the
    library."""
    if (lib := library()) is None:
        return False
    lib.az_sample(_at(bone), len(bone) // 15, _at(index), len(index) // 14, _at(keys), times, nt, q, t)
    return True


def heights(parent: array, bone: array, q: int, t: int, nt: int, out: int) -> bool:
    """``_player_crossfade._heights`` (no points) of a pose's ``q`` and
    ``t`` (bones x ``nt`` x 4 and x 3, addresses) into ``out`` (bones x
    ``nt``); False without the library."""
    if (lib := library()) is None:
        return False
    scratch = array("d", bytes(56 * len(parent)))
    lib.az_heights(_at(parent), _at(bone), len(parent), q, t, nt, out, _at(scratch))
    return True


def skinned(b: int, w: int, u: int, n: int, r: int, o: int, nb: int, normals: bool, out: int) -> bool:
    """``jiggle._skinned`` of ``n`` points (their 4 bones ``b``, int64,
    weights ``w`` and places ``u``) by ``nb`` bones' rotations ``r`` (3x3)
    and origins ``o`` into ``out`` (n x 3): the numpy buffers' addresses;
    False without the library or for a bone past ``nb`` (the twin's)."""
    return (lib := library()) is not None and lib.az_skinned(b, w, u, n, r, o, nb, int(normals), out) == 0


def signed(p: int, n: int, x: int, normals: int, nx: int, reach: float, cell: float, d: int, near: int) -> bool:
    """``jiggle._signed`` of ``n`` points ``p`` (n >= 1) from ``nx`` skin
    points ``x`` with ``normals``: their distances into ``d`` and nearest
    normals into ``near`` (addresses); False without the library."""
    if (lib := library()) is None:
        return False
    keep = array("q", bytes(8 * nx))
    return lib.az_signed(p, n, x, normals, nx, reach, cell, d, near, _at(keep)) == 0


_EIGHT = bytes(64)


def ray(row: array, p, origin) -> tuple | None | bool:
    """``mesh_edit._ray_at`` of the point ``p`` for the round side
    ``row`` packs (``mesh_edit._ray_row``; from ``origin``, a pair's,
    where given): ``(u, r, R, k, w, ramp)``, ``None`` at the origin, or
    ``False`` without the library or where the twin raises (a division
    by zero), which then answers."""
    if (lib := library()) is None:
        return False
    out = array("d", _EIGHT)
    at = out.buffer_info()[0]
    if origin is None:
        code = lib.az_ray(row.buffer_info()[0], p[0], p[1], p[2], 0, 0.0, 0.0, 0.0, at)
    else:
        code = lib.az_ray(row.buffer_info()[0], p[0], p[1], p[2], 1, origin[0], origin[1], origin[2], at)
    if code == 0:
        return (out[0], out[1], out[2]), out[3], out[4], out[5], out[6], out[7]
    return None if code == 1 else False


def thin(keys, eps: float, rest: float) -> list[int] | None | bool:
    """``clip_import._thin_kept``: the keys (time, value, in, out) of a
    track thinned within ``eps`` keep, by index, or ``None`` where it
    holds ``rest`` within ``eps`` throughout; ``False`` without the library
    or where the twin answers (a time not finite or not after the one
    before)."""
    if (lib := library()) is None or not keys:
        return False
    n = len(keys)
    try:
        flat = array("d", [x for key in keys for x in key])
    except TypeError:
        return False
    if len(flat) != 4 * n:
        return False
    kept, work = array("q", bytes(8 * n)), array("d", bytes(40 * n))
    code = lib.az_thin(_at(flat), n, eps, rest, _at(work), _at(kept))
    if code == -1:
        return None
    return kept[:code].tolist() if code > 0 else False


def smooth(samples: Sequence, loop: bool, kernel: Sequence[int]) -> list | None:
    """``jiggle._smooth`` of ``samples`` (3 floats each) by the integer
    weights ``kernel``: each one's 3-tuple, or ``None`` without the
    library or where the twin answers (a loop of fewer than 2 samples,
    weights summing to 0, a weight not an int under 2**53)."""
    if (lib := library()) is None or not all(type(c) is int and abs(c) < 1 << 53 for c in kernel) or \
            abs(sum(kernel)) >= 1 << 53:
        return None
    n = len(samples)
    try:
        flat = array("d", [x for p in samples for x in p])
    except TypeError:
        return None
    if len(flat) != 3 * n:
        return None
    out, weights = array("d", bytes(24 * n)), array("q", kernel)
    if lib.az_smooth(_at(flat), n, int(loop), _at(weights), len(weights), _at(out)) != 0:
        return None
    return [(out[3 * i], out[3 * i + 1], out[3 * i + 2]) for i in range(n)]


# ---- the paint and the textures (native/paint.c) ---------------------------------------------------------------------
def dxt(rgba: bytes, h: int, w: int, dxt1: bool) -> bytes | None:
    """``textures._dxt`` of a level's ``h`` x ``w`` RGBA8 texels (rows
    top down): its BC1 (``dxt1``) or BC2 blocks, or ``None`` without the
    library."""
    if (lib := library()) is None:
        return None
    out = bytearray(((h + 3) // 4) * ((w + 3) // 4) * (8 if dxt1 else 16))
    return bytes(out[:lib.az_dxt(rgba, h, w, int(dxt1), _buf(out))])


def atan2(y: int, x: int, n: int, out: int) -> bool:
    """``fdlibm.atan2(y[i], x[i])`` of ``n`` points into ``out`` (the
    doubles' addresses); False without the library."""
    return (lib := library()) is not None and lib.az_atan2(y, x, n, out) == 0


def raster(p: int, m: int, size: int, tid: int, bary: int) -> bool:
    """``paint._raster`` of ``m`` triangles whose corners' UVs times
    ``size`` are ``p`` (m x 3 x 2 doubles) into ``tid`` (size x size
    int64, each -1) and ``bary`` (size x size x 3 doubles, each 0): the
    buffers' addresses; False without the library or where the twin
    answers (a corner 2**40 or more from 0 or -0.0, which it draws; one
    not finite, which it refuses), nothing written then."""
    return (lib := library()) is not None and lib.az_raster(p, m, size, tid, bary) == 0


def rays(row: array, points: Sequence, origin) -> list | None:
    """:func:`ray` of each of ``points`` (3 floats each) in one call: each
    one's answer, ``None`` at the origin or ``False`` where the twin
    answers; ``None`` without the library."""
    if (lib := library()) is None or not points:
        return None
    n = len(points)
    try:
        flat = array("d", [x for p in points for x in p])
    except TypeError:
        return None
    if len(flat) != 3 * n:
        return None
    out, code = array("d", bytes(64 * n)), array("q", bytes(8 * n))
    g = (0.0, 0.0, 0.0) if origin is None else origin
    lib.az_rays(row.buffer_info()[0], n, _at(flat), int(origin is not None), g[0], g[1], g[2], _at(out), _at(code))
    return [((out[8 * i], out[8 * i + 1], out[8 * i + 2]), out[8 * i + 3], out[8 * i + 4], out[8 * i + 5],
             out[8 * i + 6], out[8 * i + 7]) if code[i] == 0 else None if code[i] == 1 else False for i in range(n)]


def decimate(pos: array, flags: bytes, vpoint: array, twin: array, so: array, sb: array, sw: array, sbad: bytes,
             tris: array, tp: array, alive: bytes, backed: bytes, quad: array, norm: array, count: int,
             target: float, limit: float | None) -> tuple[array, bytearray] | None:
    """``decimate.decimate``'s collapses (``native/decimate.c``) on its
    ``_Work``'s packing (``decimate._compiled``): the triangles' corners
    and which live after them, or ``None`` without the library or where
    the twin answers (a NaN, a skin it refuses). Its pool and heap grow
    until they hold the cut."""
    if (lib := library()) is None:
        return None
    n, nt = len(pos) // 3, len(tris) // 3
    bcap, hcap = 4 * n + 1024, 8 * n + 1024
    for _ in range(4):   # each pass a pool or heap twice as large, else the twin
        out_tris, out_tp, out_alive = array("q", tris), array("q", tp), bytearray(alive)
        q, nm, pf = array("d", quad), array("d", norm), bytearray(flags)
        scratch = array("q", [0]) * lib.az_decimate_need(n, nt, bcap, hcap)
        code = lib.az_decimate(n, _at(pos), _buf(pf), len(vpoint), _at(vpoint), _at(twin), _at(so), _at(sb), _at(sw),
                               sbad, nt, _at(out_tris), _at(out_tp), _buf(out_alive), backed, _at(q), _at(nm), count,
                               float(target), int(limit is not None), 0.0 if limit is None else float(limit),
                               _at(scratch), len(scratch), bcap, hcap)
        if code == 0:
            return out_tris, out_alive
        if code == 1:
            bcap *= 2
        elif code == 2:
            hcap *= 2
        else:
            return None
    return None


# ---- the springs (native/spring.c) ----------------------------------------------------------------------------------
def spring(world: array, origin: array, stride: int, col: int, n: int, num: Sequence[float], kernel: Sequence[int],
           loop: bool, sub: int, n_keys: int) -> tuple[list, tuple] | None:
    """``jiggle.keyed``'s spring of one placed bone past its parent's pose
    (``az_spring``): at each of ``n`` steps the parent's rotation and
    origin (``world`` and ``origin``, ``stride`` bones a step, the parent
    ``col``), its numbers ``num`` (``jiggle._spring_numbers``) and its
    drive's integer weights ``kernel`` (each, and their sum, a double as
    Python's arithmetic rounds it); its ``n_keys`` keys' five numbers (each
    ``sub``-th step's) and its peaks, or ``None`` without the library or
    where the twin answers (a division by zero or a weight past a double,
    which it raises)."""
    if (lib := library()) is None or not all(type(c) is int for c in kernel) or len(world) < 4 * stride * n or \
            len(origin) < 3 * stride * n:
        return None
    try:
        nums, weights, total = array("d", num), array("d", kernel), float(sum(kernel))
    except (TypeError, OverflowError):   # a number the twin's own arithmetic takes or refuses
        return None
    flat, peaks, work = array("d", bytes(40 * n_keys)), array("d", bytes(16)), array("d", bytes(144 * n))
    if lib.az_spring(_at(world), _at(origin), stride, col, n, _at(nums), _at(weights), len(weights), total, int(loop),
                     sub, n_keys, _at(flat), _at(peaks), _at(work)) != 0:
        return None
    return [tuple(flat[5 * j:5 * j + 5]) for j in range(n_keys)], (peaks[0], peaks[1])


CLEAR_SIZES = 14                          # spring.c's Z_* and N_* counts
CLEAR_NUMBERS = 12


def clear(sizes: Sequence[int], num: Sequence[float], slot: array, link: array, bone: array, world: array,
          origin: array, skin: tuple, tail: tuple, keys: array) -> list | None:
    """``jiggle._clear`` of one clip past its glue (``az_clear``): ``sizes``
    and ``num`` (spring.c's Z_* and N_*), each rig bone's ``slot`` among
    the posed ones, the ``link`` bones, their ``bone`` numbers (jo, ra and
    the parent's bind rotation), the posed bones' ``world`` and ``origin``
    at each frame, the collider's ``skin`` (B, W, U, UN) and ``tail`` (B, W,
    U, target, owner) as C-contiguous numpy buffers' addresses, and each
    link's ``keys`` (five numbers a key): each link's keys' six numbers
    where it turned, else ``None``, or ``None`` without the library or
    where the twin answers (it raises, or a turn is past the kernel)."""
    if (lib := library()) is None:
        return None
    try:
        z, nums = array("q", sizes), array("d", num)
    except (TypeError, OverflowError):
        return None
    need = array("q", bytes(16))
    lib.az_clear_need(_at(z), _at(need))
    links, n_keys = sizes[0], sizes[1]
    out, turned = array("d", bytes(48 * links * n_keys)), array("q", bytes(8 * links))
    work, iwork = array("d", [0.0]) * need[0], array("q", [0]) * need[1]   # made once (no bytes to copy: a frame's skin
    #                                                                          is most of a clip's buffers)
    if lib.az_clear(_at(z), _at(nums), _at(slot), _at(link), _at(bone), _at(world), _at(origin), *skin, *tail,
                    _at(keys), _at(out), _at(turned), _at(work), _at(iwork)) != 0:
        return None
    return [[tuple(out[6 * (n_keys * c + j):6 * (n_keys * c + j) + 6]) for j in range(n_keys)] if turned[c] else None
            for c in range(links)]


def _buf(b: bytearray) -> ctypes.c_void_p:
    """A bytearray's address for a kernel that writes it (its first byte; an empty one: none)."""
    return ctypes.addressof((ctypes.c_char * len(b)).from_buffer(b)) if b else None


def runs(old: bytes, new: bytes) -> list[tuple[int, int]] | None:
    """``[start, end)`` of each run where ``new`` differs from ``old`` (past
    its end: all of it)."""
    if (lib := library()) is None:
        return None
    cap = 1024
    while True:
        out = array("q", bytes(16 * cap))
        n = lib.az_runs(old, len(old), new, len(new), _at(out), cap)
        if n <= cap:
            return [(out[2 * i], out[2 * i + 1]) for i in range(n)]
        cap = n

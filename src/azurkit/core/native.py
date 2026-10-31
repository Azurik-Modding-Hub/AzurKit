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
for bit (``tests/test_native.py``).

The first kernel is the randomizer's reach (:func:`solve`): the solver's
least fixpoint (``planner/solver.py``'s ``Logic._solve``) over
:class:`Tables`, its graphs and rules as integer ids.
"""

from __future__ import annotations

import collections
import ctypes
import hashlib
import os
import platform
import sys
from array import array
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ABI = 1                                   # native/reach.c's ABI: a library of another one isn't loaded
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
KERNELS = ("reach",)
DEPTH = 200                               # the deepest rule the kernel evaluates (its recursion); deeper: the twin
LIMIT = 1 << 62                           # every number the kernel holds stays under it (int64); else the twin
                                          # (no number is refused for its size, D23)

_OPS = {"false": 0, "true": 1, "counter": 2, "flag": 3, "sum": 4, "and": 5, "or": 6}
_H, _G = 19, 10                           # the tables' header words and a graph's (reach.c's H_* and G_*)


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
    "kernels", "why"}`` (``why``: the reason the twins run, else None)."""
    library()
    lib, name, sha12 = _LIB
    return {"loaded": lib is not None, "library": name if lib else None, "sha12": sha12,
            "kernels": list(KERNELS) if lib else [], "why": None if lib else name}


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

    def __post_init__(self):
        self.blob, self.twin_only = _pack(self)

    def __getstate__(self):
        return {k: v for k, v in self.__dict__.items() if k not in ("_view", "_twin")}

    def __setstate__(self, state):
        self.__dict__.update(state, _view=None, _twin=None)


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
        kmax, mmax = max(kmax, len(g.credits)), max(mmax, len(g.locations))
    words[:11] = [MAGIC, ABI, n, f, nl, nc, ni, t.start, len(t.graphs), kmax, mmax]
    return array("q", words), bool(big) or max(depth, default=0) > DEPTH


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
          log: bool) -> Solved:
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
    out = (ctypes.c_uint64 * max(1, (count + 63) // 64))()
    for i in ids:
        out[i >> 6] |= 1 << (i & 63)
    return out


def _ids(words, count: int) -> frozenset[int]:
    out = []
    for w in range((count + 63) // 64):
        x = words[w]
        while x:
            low = x & -x
            out.append(w * 64 + low.bit_length() - 1)
            x ^= low
    return frozenset(out)


def _native(lib, t: Tables, graph: int, phys: int, free: int, counters: Sequence[int], held: Sequence[int],
            flags: Iterable[int], gives: Sequence[int], got: Iterable[int] | None, late: Iterable[int], traps: bool,
            log: bool) -> Solved:
    """The reach in reach.c."""
    i64, u64 = ctypes.c_int64, ctypes.c_uint64
    if t._view is None:
        view = (i64 * len(t.blob)).from_buffer(t.blob)
        ints = (i64 * 1)()
        t._view = (view, lib.az_reach_need(view, ints), ints[0])
    view, wbn, win = t._view
    n, nl, nf, nw = t.nodes, t.locations, t.flags, max(1, (t.nodes + 63) // 64)
    cap = nl + nf + 2 if log else 0
    call = (i64 * 6)(graph, phys, free, int(got is not None), int(bool(traps)), cap)
    c = (i64 * max(1, t.counters))(*counters)
    h = (i64 * max(1, len(t.items)))(*held)
    fl, gt, lt = _words(flags, nf), _words(got or (), nl), _words(late, nl)
    gv = (i64 * max(1, nl))(*gives)
    reached, safe, ph, traps_, after, freed = ((u64 * nw)() for _ in range(6))
    loc_round, flag_round = (i64 * max(1, nl))(), (i64 * max(1, nf))()
    found_log, walked_log = (u64 * max(1, cap * nw))(), (u64 * max(1, cap * nw))()
    out = (i64 * 2)()
    rc = lib.az_reach(view, call, c, h, fl, gt, lt, gv, reached, safe, ph, traps_, after, freed, loc_round,
                      flag_round, found_log, walked_log, out, (u64 * wbn)(), (i64 * win)())
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
          traps: bool = True, log: bool = False) -> Solved:
    """``Logic._solve``'s fixpoint on ``t``: the logic graph ``graph``, the
    physical ``phys`` and the trick-free physical ``free`` (``phys`` again
    when the options turn no skip on), from ``counters`` and the items
    ``held`` (``t.items``' order), the ``flags`` credited from the start,
    each location's item ``gives`` (-1: none), and with ``got`` (the
    tracker's collected locations) and ``late`` (the guardian slots among
    them collected only from the round that reaches them) or not; the traps
    only with ``traps``, each round's with ``log``. In reach.c when this
    platform's library is loaded and holds the call's numbers, else in the
    twin: the same answer."""
    nl, ni = t.locations, len(t.items)
    for i in (graph, phys, free):
        _id(i, len(t.graphs), "graph")
    if any(type(v) is not int for v in (*counters, *held)):
        raise ValueError("counters and held: each value is an integer")
    if len(counters) != t.counters or len(held) != ni or len(gives) != nl:
        raise ValueError(f"counters, held and gives: {len(counters)}, {len(held)} and {len(gives)} values for "
                         f"{t.counters} counters, {ni} items and {nl} locations")
    flags, late = [_id(x, t.flags, "flag") for x in flags], [_id(x, nl, "late") for x in late]
    got = None if got is None else [_id(x, nl, "got") for x in got]
    for loc, x in enumerate(gives):
        if type(x) is not int or not -1 <= x < ni:
            raise ValueError(f"gives: location {loc} holds {x!r}, no item id or -1")
    lib = library()
    if lib is not None and not t.twin_only:
        terms = max([len(r[2]) for r in t.rules if r[0] == "sum"] + [1])
        grow = sum(max([abs(inc) for _, inc in t.items[x]] + [0]) * abs(t.yields[loc]) + 1
                   for loc, x in enumerate(gives) if x >= 0)
        top = max([abs(v) for v in (*counters, *held)] + [0]) + grow + sum(abs(y) for y in t.yields) + 1
        if top * terms < LIMIT:
            return _native(lib, t, graph, phys, free, counters, held, flags, gives, got, late, traps, log)
    return _twin(t, graph, phys, free, counters, held, flags, gives, got, late, traps, log)

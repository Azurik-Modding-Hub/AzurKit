"""The requirement grammar (docs/RANDOMIZER_DB.md §5): one expression string
parsed into a small tuple AST, failing closed on anything it doesn't know.

The AST is ``("or", (a, b, ...))``, ``("and", (a, b, ...))`` or an atom:
``("const", bool)``, ``("counter", name, n)``, ``("flag", id)``,
``("skip", id)``, ``("barrier", id, "destroy" | (from_node, to_node))``,
``("button", id)`` or ``("event", id)``. There is no negation: logic is
monotone (RANDOMIZER_PLAN §3.1). Parsing checks syntax only; whether a
counter, flag, skip or object exists is the loader's question.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterator

COUNTERS = ("air", "water", "fire", "earth", "disca", "discw", "discf", "disce", "discl",
            "obsidian", "sapphire", "emerald", "ruby", "diamond", "life", "staff", "ammo")
DISCS = {"air": "disca", "water": "discw", "fire": "discf", "earth": "disce", "life": "discl"}  # a disc: its counter

_PART = r"[A-Za-z0-9_]+"
_ID = rf"{_PART}(?:\.{_PART})+"   # an object, flag or skip id: <level>.<part>[.<part>...] (§2.2, §4.8)
_TOKEN = re.compile(r"[^\s()&|+]+")
_ATOMS = (
    (re.compile(r"(?P<c>[a-z]+|key\.[a-z0-9_]+)>=(?P<n>\d+)"), lambda m: ("counter", m["c"], int(m["n"]))),
    # The owner's shorthand (§5.2): water1 = water>=1, discw3 = discw>=3; a+b = a & b is the tokenizer's.
    (re.compile(r"(?P<c>air|water|fire|earth|disc[awfel])(?P<n>\d)"), lambda m: ("counter", m["c"], int(m["n"]))),
    (re.compile(rf"flag:(?P<i>{_ID})"), lambda m: ("flag", m["i"])),
    (re.compile(rf"skip:(?P<i>{_ID})"), lambda m: ("skip", m["i"])),
    (re.compile(rf"barrier:(?P<i>{_ID}):(?:(?P<d>destroy)|pass:(?P<a>{_PART})->(?P<b>{_PART}))"),
     lambda m: ("barrier", m["i"], "destroy" if m["d"] else (m["a"], m["b"]))),
    (re.compile(rf"(?P<k>button|event):(?P<i>{_ID})"), lambda m: (m["k"], m["i"])),
)


class ParseError(ValueError):
    """An expression the grammar doesn't accept; the message names the token."""


def _tokens(text: str) -> list[str]:
    out, k = [], 0
    while k < len(text):
        ch = text[k]
        if ch.isspace():
            k += 1
        elif ch in "()&|+":
            out.append("&" if ch == "+" else ch)
            k += 1
        else:
            m = _TOKEN.match(text, k)
            out.append(m.group())
            k = m.end()
    return out


def _atom(tok: str, tricks: Collection[str]) -> tuple:
    if tok in ("true", "false"):
        return ("const", tok == "true")
    if tok.startswith("trick:") or tok in tricks:
        raise ParseError(f"retired token {tok!r}: a trick is a family with no tier (D113); "
                         f"name a skip, skip:<level>.<slug>")
    for pattern, build in _ATOMS:
        m = pattern.fullmatch(tok)
        if m:
            return build(m)
    raise ParseError(f"unknown token {tok!r}")


def parse(text: str, tricks: Collection[str] = ()) -> tuple:
    """Parse ``text`` into the AST above. ``tricks`` are the family names,
    refused as bare atoms with D113's message. Raises :class:`ParseError`."""
    if not isinstance(text, str):
        raise ParseError(f"not a string: {text!r}")
    toks = _tokens(text)
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1] if pos <= len(toks) else None

    def series(op, item):
        node = [item()]
        while peek() == op:
            take()
            node.append(item())
        return node[0] if len(node) == 1 else ("or" if op == "|" else "and", tuple(node))

    def expr():
        return series("|", conj)

    def conj():
        return series("&", unary)

    def unary():
        tok = take()
        if tok is None:
            raise ParseError("unexpected end")
        if tok == "(":
            inner = expr()
            if take() != ")":
                raise ParseError("missing ')'")
            return inner
        if tok in (")", "&", "|"):
            raise ParseError(f"unexpected {tok!r}")
        return _atom(tok, tricks)

    try:
        ast = expr()
        if peek() is not None:
            raise ParseError(f"trailing token {peek()!r}")
        return ast
    finally:     # expr, conj and unary call each other: a cycle a GC pass had to find, every parse (Step 2.178b)
        del expr


def atoms(ast: tuple) -> Iterator[tuple]:
    """Every atom of ``ast``, left to right."""
    if ast[0] in ("and", "or"):
        for child in ast[1]:
            yield from atoms(child)
    else:
        yield ast

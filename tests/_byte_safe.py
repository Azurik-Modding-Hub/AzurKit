"""Byte-safe failure output: a failing test never prints game bytes into a
log. ``tests/conftest.py`` loads it. Ported from Azurik_Modkit's, with its
AZ-433 residual closed (below).

- A failed comparison with a ``bytes``/``bytearray``/``memoryview``
  operand over 32 bytes reports each operand's length and
  ``sha256[:12]`` and the first differing offset, not the bytes. One of a
  list, dict or other object whose ``repr`` holds such bytes, or a str
  whose own text holds one, reports each operand's ``repr`` redacted as
  below, so pytest never builds its own diff of the bytes. ``unittest``
  (which no assert hook sees) builds its messages from reprs redacted the
  same way, before it shortens them.
- Every failure report is rewritten too, in every run (AZ-230): a
  traceback's function arguments and ``-l``'s locals, assertion
  rewriting's ``where`` values,
  ``unittest``'s diffs and captured output. ``b'…'`` reprs over 32 bytes
  and hex runs over 96 digits become ``<len, sha256[:12]>``. Adjacent
  reprs count as one, also across a failure line's ``E`` and a diff's
  ``-``/``+``/``?`` marks, as ``-vv`` and ``unittest`` wrap a long value
  into a short one a line.
- A str literal (a str's repr, or a JSON string) is read back and its
  text redacted the same way, so a bytes repr is found however often it
  was escaped; one that doesn't read back (``'C:\\Users\\…'``) keeps its
  text. A bytes repr cut off at a line's or str's end counts, and so
  does one glued to a word or quote if it holds a ``\\x`` escape
  (AZ-261). AZ-283: so does a str literal glued to a word or quote if
  it holds an escape (``x'b\\'…'``), one opened by the quote a kept
  literal closed with (``a ' and 'b\\'…'``), and a ``b'…'`` with no
  escape glued to a word or between two quotes (``xb'ABC…'``,
  ``'b'ABC…''``) if it is the bytes' own repr. AZ-297: a lone quote
  before a str literal of the other kind opens none that holds an
  escaped quote of that kind or ends at its quote (``a " and 'b\\'…'``),
  and a str literal holding an escaped quote of its own kind is a repr,
  read to its closing quote whatever bytes it holds. AZ-433: every
  ``b'…'`` or ``b"…"`` the scan left that reads back as the repr of over
  32 bytes counts, glued to anything and wherever it sits, also when it
  reads like prose or source (``xb'-the quick … dog'y``): Modkit kept
  those, and so printed about a third of such leaks. A failure line that
  merely looks like one is digested too; a lost line of text is the price.
- The scan is linear in the text (AZ-298): an escaped quote opens no
  literal, so a 1.4 MB one-line repr takes about 0.3 s, not a minute.
"""

from __future__ import annotations

import ast
import hashlib
import re
import unittest.case
import unittest.util
import warnings

import pytest

LIMIT = 32
# an escaped quote (after an odd run of backslashes) as the scan sees it: it
# opens and closes no literal, so each literal is tried from an unescaped quote
# only and the scan stays linear (AZ-298)
_SQ, _DQ = "\ue000", "\ue001"
_PAIR = re.compile(r"\\(.)", re.S)


def _masked(text: str) -> str:
    return _PAIR.sub(lambda m: {"'": "\\" + _SQ, '"': "\\" + _DQ}.get(m.group(1), m.group()), text)


# the start of a bytes literal with a \x escape before its closing quote
_ESCAPED = (r"""b'(?:\\[^x\n]|[^\\'\n])*?\\x[0-9a-f]{2}|"""
            r"""b"(?:\\[^x\n]|[^\\"\n])*?\\x[0-9a-f]{2}""")
# where a bytes literal may start inside a str literal of each kind: one with a
# \x escape anywhere, any other at a word boundary; and a '…' str never ends at
# the quote of "b' (a lone ' before a JSON string, AZ-297), nor a "…" str at that
# of 'b"
_IN_SQ = rf"""{_ESCAPED}|(?<![\w'"])b"|(?<![\w'])b'"""
_IN_DQ = rf"""{_ESCAPED}|(?<![\w'"])b'|(?<![\w"])b\""""
# a bytes literal; a str literal that holds no escaped quote of the other
# kind, which no repr or JSON string escapes (a lone " before a '…' repr closes
# at none of its quotes, AZ-297), and runs into no bytes literal's start (the
# quote in "got 'b'\x00…" or "`x`'s header: b'ABC…'" opens none) unless it
# holds an escaped quote of its own kind, as only a repr does (AZ-297); or a
# bytes literal cut off at a line's end
_SQ_STR = rf"""'(?:(?=[^'\n]*{_SQ})(?:\\[^\n{_DQ}]|[^\\'\n])*|(?:\\[^\n{_DQ}]|(?!{_IN_SQ})[^\\'\n])*)'"""
_DQ_STR = rf""""(?:(?=[^"\n]*{_DQ})(?:\\[^\n{_SQ}]|[^\\"\n])*|(?:\\[^\n{_SQ}]|(?!{_IN_DQ})[^\\"\n])*)\""""
_LITERAL = (r"""b'(?:\\.|[^\\'\n])*'|b"(?:\\.|[^\\"\n])*"|"""
            rf"""{_SQ_STR}|{_DQ_STR}|"""
            r"""b'(?:\\.|[^\\'\n])*\\?(?=\n|\Z)|b"(?:\\.|[^\\"\n])*\\?(?=\n|\Z)""")
_GAP = r"""(?:\s|(?<=\n)E(?=\s)|(?<=\s)[-+?^]+(?=\s))+"""  # space, E gutter, diff marks
# not inside a word or right after a quote, unless a str literal with an
# escape (x'b\'…') or a bytes literal with a \x escape
_START = rf"""(?:(?<![\w'"])|(?='[^'\n]*\\|"[^"\n]*\\|{_ESCAPED}))"""
_BYTES_REPR = re.compile(rf"""{_START}(?:{_LITERAL})(?:{_GAP}(?:{_LITERAL}))*""")
_ONE = re.compile(rf"""{_START}(?:{_LITERAL})""")  # one literal
# any b'…' or b"…" the scan left: glued to a word or a quote, after rb, …
_GLUED = re.compile(r"""b'(?:\\.|[^\\'\n])*'|b"(?:\\.|[^\\"\n])*\"""")
_HEX_RUN = re.compile(r"(?:[0-9A-Fa-f]{2}[ :]?){48,}[0-9A-Fa-f]+")


def _digest(data: bytes, unit: str = "bytes") -> str:
    return f"<{len(data)} {unit}, sha256 {hashlib.sha256(data).hexdigest()[:12]}>"


def _first_difference(a: bytes, b: bytes) -> int:
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


def pytest_assertrepr_compare(op, left, right):
    sides = [bytes(x) if isinstance(x, (bytes, bytearray, memoryview)) else None
             for x in (left, right)]
    if all(s is None or len(s) <= LIMIT for s in sides):
        try:  # a list, dict, str or object holding long bytes
            shown = [repr(x) for x in (left, right)]
            redacted = [_redact(r) for r in shown]
        except Exception:  # a faulty __repr__: pytest's own hook explains it
            return None
        return None if redacted == shown else [f"{redacted[0]} {op} {redacted[1]}"]
    a, b = (_digest(s) if s is not None else type(x).__name__
            for s, x in zip(sides, (left, right)))
    lines = [f"{a} {op} {b}"]
    if op == "==" and None not in sides:
        lines.append(f"first differing offset {_first_difference(*sides):#x}")
    return lines


def _redact_repr(text: str, scan: str, m: re.Match) -> str:
    """The literals ``m`` found in ``scan`` (``text`` masked), redacted
    from ``text``."""
    group, at = text[m.start():m.end()], m.start()
    literals = [text[at + r.start():at + r.end()] for r in re.finditer(_LITERAL, scan[at:m.end()])]
    try:
        with warnings.catch_warnings():  # a repr cut short may hold a bad escape
            warnings.simplefilter("ignore")
            values = [ast.literal_eval(s) for s in literals]
        if all(isinstance(v, str) for v in values):  # a str's repr escapes what it holds
            inner = "".join(values)
            return group if (redacted := _redact(inner)) == inner else repr(redacted)
        data, unit = b"".join(values), "bytes"
    except (ValueError, SyntaxError, TypeError):  # cut short ("[852 chars]", "..."), or mixed
        if not any(s.startswith("b") for s in literals):  # text, not a repr ('C:\Users\…')
            return group
        data, unit = group.encode(errors="surrogatepass"), "repr characters"
    return _digest(data, unit) if len(data) > LIMIT else group


def _glued(m: re.Match) -> str:
    """A ``b'…'`` or ``b"…"`` the scan left counts if it is the repr of
    over 32 bytes, glued to anything and wherever it sits (AZ-297,
    AZ-433). Never a quoted ``'b'`` (or a quoted word's last ``b'``) then
    a space or comma, up to an empty literal (``'b' in … b''``, ``'rb' if
    … else ''``, AZ-283): source, whose bytes would end in `` b``."""
    text, group, start = m.string, m.group(), m.start()
    while start and text[start - 1] not in " \t\n'\"":
        start -= 1
    before, after = text[start - 1:start], text[m.end():m.end() + 1]
    if ((start == m.start() or before == "'") and re.match(r"b'[\s,]", group)
            and re.search(r"\sb?'\Z", group) and after == "'"):  # '|b' in … b|''
        return group
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            data = ast.literal_eval(group)
    except (ValueError, SyntaxError):
        return group
    return _digest(data) if len(data) > LIMIT and repr(data) == group else group


def _redact(text: str) -> str:
    scan, out, pos = _masked(text), [], 0
    while m := _BYTES_REPR.search(scan, pos):
        # a kept literal may have closed with the quote that opens the next one
        if ((new := _redact_repr(text, scan, m)) == text[m.start():m.end()]
                and (r := _ONE.match(scan, m.end() - 1))
                and (s := _redact_repr(text, scan, r)) != text[r.start():r.end()]):
            m, new = r, s
        out += text[pos:m.start()], new
        pos = m.end()
    text, out, pos = "".join(out) + text[pos:], [], 0
    while m := _GLUED.search(text, pos):
        if (new := _glued(m)) == m.group() and m.group()[-2] == "b":  # its quote may open the next
            out.append(text[pos:m.end() - 2])
            pos = m.end() - 2
        else:
            out += text[pos:m.start()], new
            pos = m.end()
    text = "".join(out) + text[pos:]
    return _HEX_RUN.sub(lambda m: _digest(m.group().encode(), "hex characters"), text)


class _Shown(str):
    __repr__ = str.__str__


_UNITTEST_REPR = unittest.util.safe_repr


def _unittest_repr(obj, short=False):
    """unittest's ``safe_repr``, redacted before unittest shortens it (its
    ``{'k':[858 chars]…`` cut drops the ``b'`` and keeps 41 characters)."""
    return _UNITTEST_REPR(_Shown(_redact(_UNITTEST_REPR(obj))), short)


def pytest_configure(config):
    patch = pytest.MonkeyPatch()
    for module in (unittest.util, unittest.case):  # case imported its own name
        patch.setattr(module, "safe_repr", _unittest_repr)
    config.add_cleanup(patch.undo)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.failed:
        text = str(report.longrepr)
        if (redacted := _redact(text)) != text:  # else keep the report's own form
            report.longrepr = redacted
        report.sections = [(title, _redact(body)) for title, body in report.sections]
    return report

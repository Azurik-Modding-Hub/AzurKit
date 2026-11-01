"""How deep a JSON text nests, read before anything parses it (Step 4.4ci2).

``json`` refuses deep nesting only where its parser runs out of C stack,
which Python 3.14 measures per thread and so per platform: 60,000 brackets
raise ``RecursionError`` on this Mac's main thread and parse whole on CI's
Linux and Intel Mac runners and in any other thread here. An untrusted
text (a preset's link, a content manifest) is refused past its depth by
:func:`deeper` instead, the same on every platform and in every thread, in
time linear in the text: its brackets counted outside its strings, which is
JSON's own nesting for a JSON text."""

from __future__ import annotations

import re

_STRING = re.compile(r'"(?:[^"\\]|\\.)*+"?', re.S)   # one that never closes runs to the end: it can't backtrack
_NOT_BRACKET = re.compile(r"[^\[\]{}]+")


def deeper(text: str, limit: int) -> bool:
    """Whether ``text``'s brackets outside its strings nest past ``limit``
    (an ill-formed text is the parser's to name, unless it nests past it)."""
    depth = 0
    for bracket in _NOT_BRACKET.sub("", _STRING.sub("", text)):
        depth += 1 if bracket in "[{" else -1
        if depth > limit:
            return True
    return False

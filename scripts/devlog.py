"""devlog: the developer log's stale bullets (Step 4.4dx1).

``docs/DEVLOG.md`` merges with git's built-in union driver (``.gitattributes``),
so lanes that each add a bullet at a section's end never conflict. Union keeps
both sides of every hunk, so a lane whose later commit edits its own earlier
bullet, rebased onto a main that moved, keeps the old line beside the new one.
:func:`stale` names each such pair in a release; ``tests/test_contracts.py``
(the lint set) and ``scripts/land.py`` refuse a log that holds one. Stdlib only.
"""

from __future__ import annotations

import difflib
import re

LOG = "docs/DEVLOG.md"
TITLE = re.compile(r"^- \*\*(.+?)\*\*")
STEP = re.compile(r"\bSteps? ([^\s,;:)]+)")
#: Two bullets of a release and step whose words are this alike are one bullet twice: an edit a lane makes to its
#: own bullet keeps most of them, and today's log's two most alike distinct bullets of a step share a third.
ALIKE = 0.6


def stale(text: str) -> list[str]:
    """Each pair of bullets in one release (a ``## `` section) that is one
    bullet twice: the same bold title, or the same step (its first ``Step``,
    or none) and words :data:`ALIKE` alike or more."""
    found, release = [], []
    for n, line in enumerate([*text.splitlines(), "## end"], 1):
        if line.startswith("## "):
            found += _pairs(release)
            release = []
        elif line.startswith("- "):
            title, step = TITLE.match(line), STEP.search(line)
            release.append((n, title and title.group(1), step and step.group(1), line.split()))
    return found


def _pairs(bullets: list[tuple[int, str | None, str | None, list[str]]]) -> list[str]:
    found = []
    for i, (n, title, step, words) in enumerate(bullets):
        for m, other, its_step, more in bullets[i + 1:]:
            if title is not None and title == other:
                found.append(f"{LOG}: lines {n} and {m} are both **{title}**: keep one (a union merge keeps a lane's "
                             f"edited bullet beside its old line)")
            elif step == its_step and (alike := _alike(words, more)) >= ALIKE:
                found.append(f"{LOG}: lines {n} and {m} are one bullet twice ({alike:.0%} of their words alike: "
                             f"{' '.join(words[1:7])} ...): keep the newer (a union merge keeps a lane's edited "
                             f"bullet beside its old line)")
    return found


def _alike(words: list[str], more: list[str]) -> float:
    """The share of two bullets' words alike (difflib's ratio), or 0 once
    its quick bounds fall under :data:`ALIKE`."""
    sm = difflib.SequenceMatcher(None, words, more, autojunk=False)
    return sm.ratio() if sm.real_quick_ratio() >= ALIKE and sm.quick_ratio() >= ALIKE else 0.0

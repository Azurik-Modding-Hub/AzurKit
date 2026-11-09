"""devlog: the developer log's entries, one file each, joined at a release (Step 4.28f, Modkit's ``scripts/devlog.py``
of Step 2.212), and its stale bullets (Step 4.4dx1).

Each change's entry is its own file, ``docs/devlog/<section>/<step>-<slug>.md``, so two lanes adding entries never
touch the same lines and a rebase never copies one. ``<section>`` is ``added``, ``changed``, ``removed`` or ``fixed``;
the name is lower-case letters, digits, dots and hyphens, ending ``.md``; the file is one Markdown bullet (a first
line ``- ...``, any further line indented two spaces, no blank line) ending in a newline. The join is in a stable
order: the sections in that order (Keep a Changelog's), in each the files by name with numbers compared as numbers
(``2.9`` before ``2.10``). :func:`problems` names, each by file, a malformed file, an entry held twice (the same
text, or the same bold title and first step, in two files or already released in DEVLOG.md) and a bullet under
DEVLOG.md's ``[Unreleased]`` (the old way); ``tests/test_contracts.py`` (the lint set) runs it.

    uv run --locked python scripts/devlog.py                                          # print the joined [Unreleased]
    uv run --locked python scripts/devlog.py --release "1.0.2 (November 8, 2026)" --remove

``--release TITLE`` writes the joined section into DEVLOG.md as ``## [TITLE]``, above the newest release;
``--remove`` (only with it) deletes the entry files it joined. Exit 0 done, 1 refused (nothing written), 2 a usage
error.

``docs/DEVLOG.md`` merges with git's built-in union driver (``.gitattributes``), so lanes that each add a bullet at a
section's end never conflict. Union keeps both sides of every hunk, so a lane whose later commit edits its own
earlier bullet, rebased onto a main that moved, keeps the old line beside the new. :func:`stale` names each such pair
in a release; ``tests/test_contracts.py`` (the lint set) and ``scripts/land.py`` refuse a log that holds one. Stdlib
only.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = "docs/DEVLOG.md"
FOLDER = "docs/devlog"
SECTIONS = ("added", "changed", "removed", "fixed")
TITLE = re.compile(r"^- \*\*(.+?)\*\*")
STEP = re.compile(r"\bSteps? ([^\s,;:)]+)")
#: Two bullets of a release and step whose words are this alike are one bullet twice: an edit a lane makes to its
#: own bullet keeps most of them, and today's log's two most alike distinct bullets of a step share a third.
ALIKE = 0.6
_NAME = re.compile(r"[a-z0-9][a-z0-9.-]*\.md")
_WHERE = ("each entry is its own file, docs/devlog/<added|changed|removed|fixed>/<step>-<slug>.md "
          "(docs/DEVLOG.md's [Unreleased] says how)")


class Refused(Exception):
    """The entries can't be joined; ``args[0]`` holds one line a problem."""


def _bullets(text: str, first: int = 1) -> list[tuple[int, str]]:
    """Each Markdown bullet in ``text`` with its wrapped lines, and the line it starts on."""
    out: list[list] = []
    cur = None
    for n, line in enumerate(text.splitlines(), first):
        if line.startswith("- "):
            cur = [n, line]
            out.append(cur)
        elif cur is not None and line.startswith("  ") and line.strip():
            cur[1] += "\n" + line
        else:
            cur = None
    return [(n, t) for n, t in out]


def _keys(entry: str) -> list[str]:
    """What makes two entries the same one: their text, and their bold title with its first step."""
    flat = " ".join(entry.split())
    keys = [flat]
    if m := re.match(r"- \*\*(.+?)\*\* \(([^)]*)", flat):
        if step := re.search(r"\bSteps? ([\w.-]+)", m[2]):
            keys.append(f"**{m[1]}** (Step {step[1]})")
    return keys


def _natural(path: Path) -> list:
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", path.name)]


def _unreleased(text: str) -> tuple[int, int] | None:
    """Where DEVLOG.md's [Unreleased] section's body starts and ends (the next ``##`` heading or the end)."""
    if (m := re.search(r"^## \[Unreleased\]\n", text, re.M)) is None:
        return None
    end = text.find("\n## ", m.end())
    return m.end(), len(text) if end == -1 else end + 1


def read(root: Path = REPO) -> tuple[dict[str, list[tuple[Path, str]]], list[str]]:
    """The entry files of each section in join order, with their text, and every problem found."""
    folder, log = root / FOLDER, root / LOG
    found: dict[str, list[tuple[Path, str]]] = {s: [] for s in SECTIONS}
    problems: list[str] = []
    for path in sorted(folder.rglob("*")) if folder.is_dir() else []:
        parts = path.relative_to(folder).parts
        if path.is_dir() or any(p.startswith(".") for p in parts):   # .DS_Store and the like
            continue
        rel = path.relative_to(root).as_posix()
        if len(parts) != 2 or parts[0] not in SECTIONS or not _NAME.fullmatch(parts[1]):
            problems.append(f"{rel}: not docs/devlog/<{'|'.join(SECTIONS)}>/<step>-<slug>.md "
                            "(lower-case letters, digits, dots and hyphens)")
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.split("\n")
        if not (text.endswith("\n") and lines[0].startswith("- ") and lines[0][2:].strip()
                and all(line.startswith("  ") and line.strip() for line in lines[1:-1])):
            problems.append(f"{rel}: not one Markdown bullet (a first line '- ...', any further line indented "
                            "two spaces, no blank line, one newline at the end)")
            continue
        found[parts[0]].append((path, text))
    seen: dict[str, str] = {}
    text = log.read_text(encoding="utf-8") if log.is_file() else ""
    if (span := _unreleased(text)) is None:
        problems.append(f"{LOG}: no '## [Unreleased]' heading")
    else:
        start, end = span
        first = text.count("\n", 0, start) + 1
        problems += [f"{LOG}:{n}: an entry under [Unreleased], the old way: {_WHERE}; move it there"
                     for n, _ in _bullets(text[start:end], first)]
        for n, entry in _bullets(text[end:], first + text.count("\n", start, end)):
            for key in _keys(entry):
                seen.setdefault(key, f"{LOG}:{n}, released")
    for section in SECTIONS:
        found[section].sort(key=lambda pt: _natural(pt[0]))
        for path, entry in found[section]:
            rel = path.relative_to(root).as_posix()
            if (same := next((seen[k] for k in _keys(entry) if k in seen), None)) is not None:
                problems.append(f"{rel}: the same entry as {same}; keep one")
            for key in _keys(entry):
                seen.setdefault(key, rel)
    return found, problems


def problems(root: Path = REPO) -> list[str]:
    return read(root)[1]


def joined(root: Path = REPO, title: str = "Unreleased") -> str:
    """The entries as one ``## [title]`` section, its ``###`` sections in order."""
    found, bad = read(root)
    if bad:
        raise Refused("\n".join(bad))
    parts = [f"## [{title}]"] + [f"### {s.capitalize()}\n" + "".join(t for _, t in found[s]).rstrip("\n")
                                 for s in SECTIONS if found[s]]
    return "\n\n".join(parts) + "\n"


def release(root: Path, title: str, remove: bool = False) -> str:
    """Write the joined entries into docs/DEVLOG.md as ``## [title]`` above the newest release, and with
    ``remove`` delete the entry files; a line saying what was done."""
    found, bad = read(root)
    count = sum(len(v) for v in found.values())
    log = root / LOG
    text = log.read_text(encoding="utf-8")
    if not bad and not count:
        bad = [f"{FOLDER}/: no entry to release"]
    if not bad and f"\n## [{title}]\n" in text:
        bad = [f"{LOG} already holds a release '## [{title}]'"]
    if bad:
        raise Refused("\n".join(bad))
    end = _unreleased(text)[1]
    log.write_text(text[:end].rstrip("\n") + "\n\n" + joined(root, title) + ("\n" + text[end:] if text[end:] else ""),
                   encoding="utf-8", newline="\n")
    if remove:
        for path, _ in (pt for s in SECTIONS for pt in found[s]):
            path.unlink()
        for folder in (root / FOLDER / s for s in SECTIONS):
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
    sizes = ", ".join(f"{s} {len(found[s])}" for s in SECTIONS if found[s])
    return (f"{LOG}: '## [{title}]' holds {count} entries ({sizes})"
            + (f"; deleted their {count} files" if remove else "; their files are kept (--remove deletes them)"))


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print the developer log's entries joined, or write them into "
                                             "docs/DEVLOG.md as a release.")
    ap.add_argument("--release", metavar="TITLE",
                    help="write the joined entries into docs/DEVLOG.md as '## [TITLE]', above the newest release")
    ap.add_argument("--remove", action="store_true", help="with --release: delete the entry files it joined")
    args = ap.parse_args(argv)
    if args.remove and not args.release:
        ap.error("--remove needs --release (the entries would be lost)")
    try:
        out = release(REPO, args.release, args.remove) + "\n" if args.release else joined(REPO)
    except Refused as exc:
        print(f"devlog: refused, nothing written:\n{exc}", file=sys.stderr)
        return 1
    print(out, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

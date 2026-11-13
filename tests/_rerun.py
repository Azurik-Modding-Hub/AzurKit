"""One automatic rerun of a failed test (D1170, Step 4.22), in every run: ``tests/conftest.py`` loads it.

A test whose setup, call or teardown fails runs once more at once, in the same session and process (an xdist
worker's own), the fixtures whose setup raised made again. The first try's failed reports are logged as ``rerun``
(``R``, ``RERUN`` with ``-v``; never a failure, never a skip), its passing call too, uncounted (a teardown's rerun
passes once), and the second try's as any test's: a test that fails
again fails the run as before, and one that passes is flaky. The summary names each flaky test with its first try's
error ("flaky: N passed on their one rerun") and that error's lines under it (:func:`_lines`), and a run with
``AZURKIT_FLAKES`` set appends a line ``<id>\\t<error>`` for each to that file as its rerun ends:
``scripts/fullsuite.py`` keeps them in the receipt (``flakes``) and its flake ledger, and CI writes them into its job's
summary (``python -m tests._rerun FILE``: :func:`summary`). Each failed try's error lines go to that file's sibling
(:data:`FAILED`) as its report comes, so a run stopped before its end (a cap, a cancelled job) loses none of them
(Step 4.37k), and CI's log prints each twice-failed test's first try from it (``python -m tests._rerun --first FILE``:
:func:`first`), which neither pytest's failures nor the summary show. The run takes the variable out of its
environment, so a pytest a test runs writes neither file. A rerun is recorded, never hidden. ``-p no:tests._rerun``
turns it off, and ``--pdb`` runs without it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import textwrap
import time
from pathlib import Path

import pytest
from _pytest.runner import runtestprotocol

RERUNS = 1                              # D1170: one rerun, never more
FLAKES = "AZURKIT_FLAKES"               # the file a run appends its flaky tests to
GROUP = re.compile(r"@[^@\[\]/:]*$")    # the xdist group a worker's id ends in (tests/conftest.py)
WHY = 200                               # a flaky test's first error, cut to this many characters on its one line
LINES = 40                              # a failed try's error lines kept (its sibling file, the summary), at most
WIDTH = 200                             # characters a kept line takes, the rest on the next (CI's log cuts at 240)
FAILED = ".failed.jsonl"                # AZURKIT_FLAKES' sibling's suffix: each failed try's error lines, as it came
CUT = 240                               # characters a line --first prints, at most (CI's log's own cut)


def _why(report) -> str:
    """The first line of a failed report's error: its crash's message, else its first ``E`` line, else its last."""
    crash = getattr(getattr(report.longrepr, "reprcrash", None), "message", None)
    lines = [line.strip() for line in (crash or report.longreprtext).splitlines() if line.strip()]
    if not crash:
        lines = [line[1:].strip() for line in lines if line.startswith("E ")] or lines[-1:]
    return f"{report.when}: {lines[0] if lines else 'failed'}".replace("\t", " ")[:WHY]


def _lines(report, root: Path | None = None) -> list[str]:
    """A failed report's error as lines: where it failed (its crash's file, under ``root``, and line), then its ``E``
    lines, dedented, else its crash's message, else its last line; at most :data:`LINES`, each cut into
    :data:`WIDTH` characters a line, so read joined it is whole."""
    crash = getattr(report.longrepr, "reprcrash", None)
    text = report.longreprtext
    said = [line[1:].rstrip() for line in text.splitlines() if line == "E" or line.startswith("E ")]
    said = (textwrap.dedent("\n".join(said)).splitlines() if said
            else getattr(crash, "message", "").splitlines() or text.strip().splitlines()[-1:])
    if crash is not None and getattr(crash, "path", None):
        where = Path(crash.path)
        with contextlib.suppress(ValueError, TypeError):
            where = where.relative_to(root)
        said.insert(0, f"at {where.as_posix()}:{crash.lineno}")
    return [line[at:at + WIDTH] for line in said for at in range(0, max(len(line), 1), WIDTH)][:LINES]


def _again(item) -> None:
    """Let the rerun set up again each fixture whose setup raised (pytest keeps its error for the fixture's scope):
    finished as its scope's end would, with the rerun's request (``runtestprotocol`` makes one only when none is)."""
    if hasattr(item, "_initrequest"):
        item._initrequest()
    for fixturedefs in getattr(getattr(item, "_fixtureinfo", None), "name2fixturedefs", {}).values():
        for fixturedef in fixturedefs:
            if fixturedef.cached_result is not None and fixturedef.cached_result[2] is not None:
                with contextlib.suppress(Exception):   # its finalizers' (a fixture that raised has done nothing)
                    fixturedef.finish(item._request)


class Reruns:
    """The rerun (:func:`pytest_runtest_protocol`) and its record, one a session (a pytester run's its own)."""

    def __init__(self, config) -> None:
        self.reran: dict[str, str] = {}   # id -> its first try's error
        self.first: dict[str, list[str]] = {}   # id -> its first try's error's lines
        self.passed: set[str] = set()
        self.failed: set[str] = set()
        self.written: set[str] = set()   # the flaky tests written to the flakes file
        self.root = Path(config.rootpath)
        # the run's flakes file (not a worker's: the run's own process writes; nor a pytest a test runs: none is left)
        self.flakes = None if hasattr(config, "workerinput") else os.environ.pop(FLAKES, None)

    def _write(self, suffix: str, text: str) -> None:
        """``text`` appended at once to the flakes file, or with ``suffix`` to its sibling."""
        path = Path(self.flakes)
        with open(path.with_suffix(suffix) if suffix else path, "a", encoding="utf-8") as out:
            out.write(text)

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item, nextitem):
        if item.config.getoption("usepdb", False):
            return None
        for left in range(RERUNS, -1, -1):
            item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
            reports = runtestprotocol(item, nextitem=nextitem, log=False)
            again = left > 0 and any(report.failed for report in reports)
            for report in reports:
                if again and (report.failed or report.when == "call"):
                    report.outcome = "rerun"
                item.ihook.pytest_runtest_logreport(report=report)
            item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
            if not again:
                break
            _again(item)
        return True

    @pytest.hookimpl(tryfirst=True)
    def pytest_report_teststatus(self, report):
        if report.outcome == "rerun":   # a first try's passing call (no error) counts as nothing
            return ("rerun", "R", ("RERUN", {"yellow": True})) if report.longrepr is not None else ("", "", "")
        return None

    def pytest_runtest_logreport(self, report):
        case, first = GROUP.sub("", report.nodeid), report.outcome == "rerun"
        if first:
            if report.longrepr is not None:
                self.reran.setdefault(case, _why(report))
                self.first.setdefault(case, _lines(report, self.root))
        elif report.failed:
            self.failed.add(case)
        elif report.when == "call" and report.passed:
            self.passed.add(case)
        if not self.flakes:
            return
        if report.longrepr is not None and (first or report.failed):   # a failed try, as it came
            tried = 1 if first or case not in self.reran else 2
            self._write(FAILED, json.dumps({"test": case, "when": report.when, "try": tried,
                                            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                            "lines": _lines(report, self.root)}) + "\n")
        if (report.when == "teardown" and not first and case in self.reran and case in self.passed
                and case not in self.failed | self.written):   # its rerun's end: flaky
            self.written.add(case)
            self._write("", f"{case}\t{self.reran[case]}\n")

    def flaky(self) -> dict[str, str]:
        """``{id: its first try's error}`` of each test that passed its rerun."""
        return {case: why for case, why in sorted(self.reran.items()) if case in self.passed - self.failed}

    @pytest.hookimpl(trylast=True)   # after tests/conftest.py's tier lines, from which CI's tier prints its log
    def pytest_terminal_summary(self, terminalreporter):
        if flaky := self.flaky():
            terminalreporter.write_line(f"flaky: {len(flaky)} passed on their one rerun (recorded, D1170)", yellow=True)
            for case, why in flaky.items():
                terminalreporter.write_line(f"  {case}: {why}")
                for line in self.first.get(case, []):   # its first try's error whole, past WHY's one line
                    terminalreporter.write_line(f"    {line}")

    def pytest_sessionfinish(self, session):
        if self.flakes and (left := {case: why for case, why in self.flaky().items() if case not in self.written}):
            self.written |= set(left)   # each its rerun's end didn't write
            self._write("", "".join(f"{case}\t{why}\n" for case, why in left.items()))


def pytest_configure(config):
    config.pluginmanager.register(Reruns(config), "azurkit-reruns")


def summary(text: str) -> str:
    """A job summary's Markdown of a flakes file's ``text`` (empty for none): each test's id and first error."""
    rows = dict(line.partition("\t")[::2] for line in text.splitlines() if line.strip())
    if not rows:
        return ""
    return (f"### Flaky: {len(rows)} passed on their one rerun (D1170: recorded, not a block)\n\n"
            + "".join(f"- `{case}`: {why}\n" for case, why in sorted(rows.items())))


def first(text: str) -> str:
    """Each test that failed twice in a :data:`FAILED` file's ``text`` (it has a second try's row): its first try's
    rows, each its test, phase and time, then its error lines, under a heading line; empty for none. Its first try's
    report is a rerun's, which pytest's failures and the summary leave out, so a stall's first words (what stopped,
    WebKit's ended pages, Firefox's log) were never printed (D1260: CI run 43431651205). A torn line (a run stopped
    as it wrote) is passed over; each line is cut at :data:`CUT`."""
    rows = []
    for line in text.splitlines():
        with contextlib.suppress(ValueError):
            rows.append(json.loads(line))
    rows = [row for row in rows if isinstance(row, dict)]
    twice = {row.get("test") for row in rows if row.get("try") == 2}
    said = [line[:CUT] + "\n" for row in rows if row.get("test") in twice and row.get("try") == 1
            for line in (f"{row.get('test')}: its first try's {row.get('when')}, at {row.get('at')}",
                         *(f"    {line}" for line in row.get("lines", ())))]
    head = f"--- failed twice ({len(twice)}): each one's first try (tests/_rerun.py, D1170)\n"
    return head + "".join(said) if said else ""


if __name__ == "__main__":   # CI: python -m tests._rerun FILE >> "$GITHUB_STEP_SUMMARY"; --first FILE: its log
    show, path = (first, Path(sys.argv[2])) if sys.argv[1] == "--first" else (summary, Path(sys.argv[1]))
    sys.stdout.write(show(path.read_text(encoding="utf-8")) if path.is_file() else "")

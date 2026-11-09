"""One automatic rerun of a failed test (D1170, Step 4.22), in every run: ``tests/conftest.py`` loads it.

A test whose setup, call or teardown fails runs once more at once, in the same session and process (an xdist
worker's own), the fixtures whose setup raised made again. The first try's failed reports are logged as ``rerun``
(``R``, ``RERUN`` with ``-v``; never a failure, never a skip) and the second try's as any test's: a test that fails
again fails the run as before, and one that passes is flaky. The summary names each flaky test with its first try's
error ("flaky: N passed on their one rerun"), and a run with ``AZURKIT_FLAKES`` set appends a line ``<id>\\t<error>``
for each to that file: ``scripts/fullsuite.py`` keeps them in the receipt (``flakes``) and its flake ledger, and CI
writes them into its job's summary (``python -m tests._rerun FILE``: :func:`summary`). A rerun is recorded, never
hidden. ``-p no:tests._rerun`` turns it off, and ``--pdb`` runs without it.
"""

from __future__ import annotations

import contextlib
import os
import re
import sys
from pathlib import Path

import pytest
from _pytest.runner import runtestprotocol

RERUNS = 1                              # D1170: one rerun, never more
FLAKES = "AZURKIT_FLAKES"               # the file a run appends its flaky tests to
GROUP = re.compile(r"@[^@\[\]/:]*$")    # the xdist group a worker's id ends in (tests/conftest.py)
WHY = 200                               # a flaky test's first error, cut to this many characters


def _why(report) -> str:
    """The first line of a failed report's error: its crash's message, else its first ``E`` line, else its last."""
    crash = getattr(getattr(report.longrepr, "reprcrash", None), "message", None)
    lines = [line.strip() for line in (crash or report.longreprtext).splitlines() if line.strip()]
    if not crash:
        lines = [line[1:].strip() for line in lines if line.startswith("E ")] or lines[-1:]
    return f"{report.when}: {lines[0] if lines else 'failed'}".replace("\t", " ")[:WHY]


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

    def __init__(self) -> None:
        self.reran: dict[str, str] = {}   # id -> its first try's error
        self.passed: set[str] = set()
        self.failed: set[str] = set()

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item, nextitem):
        if item.config.getoption("usepdb", False):
            return None
        for left in range(RERUNS, -1, -1):
            item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
            reports = runtestprotocol(item, nextitem=nextitem, log=False)
            again = left > 0 and any(report.failed for report in reports)
            for report in reports:
                if again and report.failed:
                    report.outcome = "rerun"
                item.ihook.pytest_runtest_logreport(report=report)
            item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
            if not again:
                break
            _again(item)
        return True

    @pytest.hookimpl(tryfirst=True)
    def pytest_report_teststatus(self, report):
        if report.outcome == "rerun":
            return "rerun", "R", ("RERUN", {"yellow": True})
        return None

    def pytest_runtest_logreport(self, report):
        case = GROUP.sub("", report.nodeid)
        if report.outcome == "rerun":
            self.reran.setdefault(case, _why(report))
        elif report.failed:
            self.failed.add(case)
        elif report.when == "call" and report.passed:
            self.passed.add(case)

    def flaky(self) -> dict[str, str]:
        """``{id: its first try's error}`` of each test that passed its rerun."""
        return {case: why for case, why in sorted(self.reran.items()) if case in self.passed - self.failed}

    @pytest.hookimpl(trylast=True)   # after tests/conftest.py's tier lines, from which CI's tier prints its log
    def pytest_terminal_summary(self, terminalreporter):
        if flaky := self.flaky():
            terminalreporter.write_line(f"flaky: {len(flaky)} passed on their one rerun (recorded, D1170)", yellow=True)
            for case, why in flaky.items():
                terminalreporter.write_line(f"  {case}: {why}")

    def pytest_sessionfinish(self, session):
        if (path := os.environ.get(FLAKES)) and not hasattr(session.config, "workerinput") and (flaky := self.flaky()):
            with open(path, "a", encoding="utf-8") as out:
                out.writelines(f"{case}\t{why}\n" for case, why in flaky.items())


def pytest_configure(config):
    config.pluginmanager.register(Reruns(), "azurkit-reruns")


def summary(text: str) -> str:
    """A job summary's Markdown of a flakes file's ``text`` (empty for none): each test's id and first error."""
    rows = dict(line.partition("\t")[::2] for line in text.splitlines() if line.strip())
    if not rows:
        return ""
    return (f"### Flaky: {len(rows)} passed on their one rerun (D1170: recorded, not a block)\n\n"
            + "".join(f"- `{case}`: {why}\n" for case, why in sorted(rows.items())))


if __name__ == "__main__":   # CI: python -m tests._rerun FILE >> "$GITHUB_STEP_SUMMARY"
    path = Path(sys.argv[1])
    sys.stdout.write(summary(path.read_text(encoding="utf-8")) if path.is_file() else "")

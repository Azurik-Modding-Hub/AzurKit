"""The flake stage's repeats in one session (Step 4.4dx12): a pytest plugin
that ``scripts/fullsuite.py``'s flake stage loads (``-p scripts.flake_repeat``,
the worktree on ``sys.path`` by ``-o pythonpath=.``: ``fullsuite.REPEAT``).

``--flake-runs N`` runs each test that takes none of :data:`OWN_SESSIONS`'s
fixtures N times in this session, as cases ``<id>[<its parameters>-flake-run-K]``
(``fullsuite.split`` reads them back); one that takes one runs once, and the
stage starts a session for each of its other runs, since what a session
starts once (a browser, the wheel under Pyodide, the frozen app) is part of
what such a test's run is.
"""

from __future__ import annotations

import re

import pytest

OWN_SESSIONS = frozenset({"browser", "pyodide", "frozen_app"})
RUN = "flake-run-"


def pytest_addoption(parser):
    parser.addoption("--flake-runs", type=int, default=1, metavar="N",
                     help="run each test that takes no browser, pyodide or frozen_app fixture N times in this session")


@pytest.hookimpl(trylast=True)   # after the parametrize marks' and tests/conftest.py's: its id comes last
def pytest_generate_tests(metafunc):
    runs = metafunc.config.getoption("flake_runs")
    if runs > 1 and not OWN_SESSIONS & set(metafunc.fixturenames):
        metafunc.fixturenames.append("_flake_run")
        metafunc.parametrize("_flake_run", range(1, runs + 1), ids=lambda k: f"{RUN}{k}")


@pytest.hookimpl(wrapper=True)   # before tests/conftest.py's, which names each xdist group's case by its group
def pytest_collection_modifyitems(config, items):
    """A case's runs in one xdist group, so one worker runs them one after
    another, as its sessions did, never two at once (its id then holds the
    group past an ``@``, which ``fullsuite.case_id`` drops)."""
    for item in items:
        if "_flake_run" in getattr(getattr(item, "callspec", None), "params", {}):
            case = item.nodeid.rpartition(RUN)[0].rstrip("[-")   # its id without the run
            item.add_marker(pytest.mark.xdist_group(re.sub(r"[^\w.-]", "_", case)))
    return (yield)

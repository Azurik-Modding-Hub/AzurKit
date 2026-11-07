"""The flake stage's repeats in one session (Step 4.4dx12): a pytest plugin
that ``scripts/fullsuite.py``'s flake stage loads (``-p scripts.flake_repeat``,
the worktree on ``sys.path`` by ``-o pythonpath=.``: ``fullsuite.REPEAT``).

``--flake-runs N`` runs each test that :func:`starts_nothing_once` N times
in this session, as cases ``<id>[<its parameters>-flake-run-K]``
(``fullsuite.split`` reads them back); any other runs once, and the stage
starts a session for each of its other runs, since what a session starts
once (a browser, the wheel under Pyodide, the frozen app, the site, the
shipped database) is part of what such a test's run is.
"""

from __future__ import annotations

import re

import pytest

#: The suite's session fixtures that only hand a test a path (the verified images), so a test taking one repeats.
PATHS = frozenset({"usa_iso", "europe_iso"})
RUN = "flake-run-"


def pytest_addoption(parser):
    parser.addoption("--flake-runs", type=int, default=1, metavar="N",
                     help="run each test that takes no module- or session-scoped fixture of the suite's own (the "
                          "images' paths aside) N times in this session")


def starts_nothing_once(metafunc) -> bool:
    """Whether none of the fixtures the test reaches is one of the suite's
    own wider than a test, :data:`PATHS` aside: a fixture of a conftest
    below the root folder (``tests/conftest.py``), of a test module or of a
    class, which pytest ties to that folder's, module's or class's node,
    where it ties pytest's and a plugin's (``tmp_path_factory``, a
    parametrize mark's arguments) to the session."""
    session = metafunc.definition.session
    return not any(fixture.scope != "function" and fixture.node not in (None, session)
                   for name, fixtures in metafunc._arg2fixturedefs.items() if name not in PATHS
                   for fixture in fixtures)


@pytest.hookimpl(trylast=True)   # after the parametrize marks' and tests/conftest.py's: its id comes last
def pytest_generate_tests(metafunc):
    runs = metafunc.config.getoption("flake_runs")
    if runs > 1 and starts_nothing_once(metafunc):
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

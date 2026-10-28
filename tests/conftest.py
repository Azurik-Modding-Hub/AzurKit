"""The suite's tiers and skip rule (D26).

- A test that reads the USA image is marked ``vanilla`` (the ``usa_iso``
  fixture marks it); one that reads the Europe image is marked ``europe``
  and ``vanilla`` (``europe_iso``). Every other test is ``pure``: it needs no
  game data. ``-m "not vanilla"`` runs the pure tier, ``-m "not europe"``
  leaves out the Europe tests.
- A run that selects a test of a release whose image isn't found, or isn't
  that release's vanilla image (size and sha256), stops before running
  anything, with one message that says why. Otherwise the summary prints
  ``vanilla: N run`` and ``europe: M run``.
- A skip or an xfail fails the run unless ``tests/skip_allowlist.toml`` lists
  its test id with a regex its reason matches. The list starts empty (Q277).
- Failure output is byte-safe (``tests/_byte_safe.py``).
- Git finds a repository by the cwd alone: the variables that point it at
  one (``GIT_DIR``, which ``git rebase -x`` exports, and the rest of ``git
  rev-parse --local-env-vars``) are dropped, so a test's scratch repo is its
  own.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _var in ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
             "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE",
             "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX",
             "GIT_SHALLOW_FILE", "GIT_COMMON_DIR", "GIT_NAMESPACE"):
    os.environ.pop(_var, None)

from azurkit.core import gate  # noqa: E402

pytest_plugins = ["tests._byte_safe", "pytester"]

ALLOWED_SKIPS: dict[str, str] = tomllib.loads((ROOT / "tests" / "skip_allowlist.toml").read_text(encoding="utf-8"))
_images: dict[str, Path] = {}         # release name -> its verified image
_ran: dict[str, set[str]] = {"vanilla": set(), "europe": set()}
_gated = False


def _verify(release: gate.Release) -> Path | str:
    """The release's image, or why the run can't use one."""
    if (path := gate.find(release)) is None:
        return (f"{release.name} tests need the {release.label} image: {gate.missing(release)}, or run "
                f'`pytest -m "not {"vanilla" if release is gate.USA else "europe"}"`')
    size = path.stat().st_size
    if size == release.iso_size:
        with open(path, "rb") as f:
            sha = hashlib.file_digest(f, "sha256").hexdigest()
        if sha == release.iso_sha256:
            return path
    return (f"{path} is not the vanilla {release.label} image (size {size}, want {release.iso_size}; "
            f"sha256 checked only on a size match)")


@pytest.hookimpl(tryfirst=True)   # before -m deselects
def pytest_collection_modifyitems(config, items):
    for item in items:
        names = set(getattr(item, "fixturenames", ()))
        if "europe_iso" in names:
            item.add_marker(pytest.mark.europe)
        if names & {"usa_iso", "europe_iso"}:
            item.add_marker(pytest.mark.vanilla)
        if item.get_closest_marker("europe") and not item.get_closest_marker("vanilla"):
            raise pytest.UsageError(f"{item.nodeid}: a europe test is vanilla too (use the europe_iso fixture)")
        if not item.get_closest_marker("vanilla"):
            item.add_marker(pytest.mark.pure)


@pytest.hookimpl(trylast=True)   # after -m deselects
def pytest_collection_finish(session):
    global _gated
    needed = {gate.USA if not item.get_closest_marker("europe") else gate.EUROPE
              for item in session.items if item.get_closest_marker("vanilla")}
    for release in sorted(needed, key=gate.RELEASES.index):
        found = _verify(release)
        if isinstance(found, str):
            pytest.exit(found, returncode=pytest.ExitCode.USAGE_ERROR)
        _images[release.name] = found
    _gated = True


@pytest.fixture
def usa_iso() -> Path:
    """The verified USA image (the test is ``vanilla``)."""
    return _images["usa"]


@pytest.fixture
def europe_iso() -> Path:
    """The verified Europe image (the test is ``europe`` and ``vanilla``)."""
    return _images["europe"]


def _fail_unlisted_skip(report):
    """A skip or xfail the allow-list doesn't cover becomes a failure."""
    if report.skipped or hasattr(report, "wasxfail"):
        reason = (getattr(report, "wasxfail", "") or report.longrepr[2]).removeprefix("Skipped: ")
        allowed = ALLOWED_SKIPS.get(report.nodeid)
        if allowed is None or not re.search(allowed, reason):
            report.outcome = "failed"
            report.longrepr = f"skip not in tests/skip_allowlist.toml: {reason}"
    return report


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    return _fail_unlisted_skip((yield))


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    return _fail_unlisted_skip((yield))


def pytest_runtest_logreport(report):
    if report.when == "call":
        for tier in ("vanilla", "europe"):
            if tier in report.keywords:
                _ran[tier].add(report.nodeid)


def pytest_terminal_summary(terminalreporter):
    if _gated:
        terminalreporter.write_line(f"vanilla: {len(_ran['vanilla'])} run")
        terminalreporter.write_line(f"europe: {len(_ran['europe'])} run")

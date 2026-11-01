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
- A test that runs under Pyodide on Node takes the ``pyodide`` fixture, and
  one that drives the page in a browser the ``browser`` fixture, which runs
  it in headless Chromium, again in WebKit (Safari's engine; Step 4.1d3) and
  again in Firefox (D994), or only in those ``--browsers`` names
  (``scripts/fullsuite.py``'s changed-area runs: Chromium, D970); either
  becomes ``web``. Like the images, what they run on (Pyodide, Node for the
  first, each browser for the second; ``uv run bootstrap.py`` fetches
  Pyodide and every browser) is
  needed by a run that selects one, which otherwise stops with one message
  naming what is missing; ``-m "not web"`` opts out. The summary prints
  ``web: K run``.
- A skip or an xfail fails the run unless ``tests/skip_allowlist.toml`` lists
  its test id with a regex its reason matches. The list starts empty (Q277).
- Failure output is byte-safe (``tests/_byte_safe.py``).
- The app opens no window or browser tab in a test, or in anything a test
  starts: ``AZURKIT_NO_WINDOW`` is set for the whole run (``azurkit.app``;
  D839: the owner works on this screen). The session checks the mode first,
  in a Python of its own under the run's environment with the server,
  window and browser planted to raise, and stops before any test (any
  process) runs when it doesn't hold. The session itself never imports the
  app, so what every run loads is only what this file imports
  (``scripts/fullsuite.py``'s ``SESSION``).
- Playwright launches only headless browsers: a launch (sync or async, of
  any browser) with ``headless`` other than unset (its default) or true, or
  that leaves out its ``--headless`` argument, is refused before it starts
  anything, and ``PWDEBUG`` (or its npm forms), which opens a headed
  browser, is dropped. The session checks this guard too, and stops when it
  doesn't hold.
- Git finds a repository by the cwd alone: the variables that point it at
  one (``GIT_DIR``, which ``git rebase -x`` exports, and the rest of ``git
  rev-parse --local-env-vars``) are dropped, so a test's scratch repo is its
  own.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import os
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest
from _pytest.nodeid import NodeId

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

for _var in ("GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS", "GIT_CONFIG_COUNT",
             "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE", "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE",
             "GIT_INDEX_FILE", "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX",
             "GIT_SHALLOW_FILE", "GIT_COMMON_DIR", "GIT_NAMESPACE"):
    os.environ.pop(_var, None)
os.environ["AZURKIT_NO_WINDOW"] = "1"   # azurkit.app.NO_WINDOW, before anything imports the app
for _var in ("PWDEBUG", "npm_config_pwdebug", "npm_package_config_pwdebug"):   # Playwright's debug mode
    os.environ.pop(_var, None)          # (and its npm forms): a headed browser and its inspector

from playwright._impl._browser_type import BrowserType as _BrowserType  # noqa: E402

from azurkit.core import gate  # noqa: E402
from scripts import web_tools  # noqa: E402
from tests import _pyodide  # noqa: E402

pytest_plugins = ["tests._byte_safe", "pytester"]

ALLOWED_SKIPS: dict[str, str] = tomllib.loads((ROOT / "tests" / "skip_allowlist.toml").read_text(encoding="utf-8"))
_images: dict[str, Path] = {}         # release name -> its verified image
_ran: dict[str, set[str]] = {"vanilla": set(), "europe": set(), "web": set()}
_ungrouped: dict[str, str] = {}       # a grouped test's id (its "@group" suffix, D991) -> its id
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


#: ``app.main()`` with its server, window and browser planted to raise: what it returns, or that it reached one.
_NO_WINDOW = """import contextlib, io
from azurkit import app

class Opened(Exception):
    pass

def opened(*args, **kwargs):
    raise Opened

app.serve = app._window = app.webbrowser.open = opened
with contextlib.redirect_stderr(io.StringIO()):
    try:
        code = app.main()
    except Opened:
        code = "the window path"
print(code)
"""


class _Headed(AssertionError):
    """A Playwright launch that isn't headless (D839)."""


def _headless_only(launch):
    """Playwright's ``launch``, refusing one that isn't headless."""
    signature = inspect.signature(launch)

    @functools.wraps(launch)
    def checked(*args, **kwargs):
        given = signature.bind(*args, **kwargs).arguments
        dropped = given.get("ignoreDefaultArgs") or ()
        if given.get("headless") not in (None, True) or dropped is True or any("headless" in a for a in dropped):
            raise _Headed(f"BrowserType.{launch.__name__}: a browser that isn't headless: no test opens a window on "
                          "the owner's screen (D839)")
        return launch(*args, **kwargs)
    return checked


for _name in ("launch", "launch_persistent_context"):   # the impl's: the sync and async APIs both call it
    setattr(_BrowserType, _name, _headless_only(getattr(_BrowserType, _name)))


def pytest_sessionstart(session):
    """The no-window mode holds before a test starts anything (D839):
    ``app.main()`` returns 1 without reaching its planted server, window or
    browser (:data:`_NO_WINDOW`, in this run's environment), and a headed
    Playwright launch is refused, else the run stops here."""
    try:
        _BrowserType.launch(None, headless=False).close()   # unguarded, a coroutine that never runs
    except _Headed:
        pass
    else:
        pytest.exit("Playwright's launch isn't held to headless: no test runs (D839)",
                    returncode=pytest.ExitCode.USAGE_ERROR)

    done = subprocess.run([sys.executable, "-I", "-c", _NO_WINDOW], capture_output=True, text=True, timeout=300)
    if (code := done.stdout.strip() or f"no answer: {done.stderr.strip()[-500:]}") != "1":
        pytest.exit(f"AZURKIT_NO_WINDOW doesn't keep azurkit.app's window shut (app.main() gave {code}, want 1): "
                    "no test runs (D839)", returncode=pytest.ExitCode.USAGE_ERROR)


def pytest_addoption(parser):
    parser.addoption("--browsers", default=",".join(web_tools.BROWSERS), metavar="NAMES",
                     help=f"the browsers the browser fixture drives the page in, comma-separated (default: every one, "
                          f"{','.join(web_tools.BROWSERS)})")


def pytest_generate_tests(metafunc):
    """A ``browser`` test runs once in each browser ``--browsers`` names."""
    if "browser" in metafunc.fixturenames:
        names = metafunc.config.getoption("browsers").split(",")
        if set(names) - set(web_tools.BROWSERS):
            raise pytest.UsageError(f"--browsers takes names of {', '.join(web_tools.BROWSERS)}, not {names}")
        metafunc.parametrize("browser", [n for n in web_tools.BROWSERS if n in names], indirect=True, scope="module")


@pytest.hookimpl(tryfirst=True)   # before -m deselects
def pytest_collection_modifyitems(config, items):
    for item in items:
        names = set(getattr(item, "fixturenames", ()))
        if "europe_iso" in names:
            item.add_marker(pytest.mark.europe)
        if names & {"usa_iso", "europe_iso"}:
            item.add_marker(pytest.mark.vanilla)
        if names & {"pyodide", "browser"}:
            item.add_marker(pytest.mark.web)
        if "frozen_app" in names:   # one frozen app a run: --dist loadgroup keeps its tests on one worker (D991)
            item.add_marker(pytest.mark.xdist_group("frozen_app"))
        if item.get_closest_marker("europe") and not item.get_closest_marker("vanilla"):
            raise pytest.UsageError(f"{item.nodeid}: a europe test is vanilla too (use the europe_iso fixture)")
        if not item.get_closest_marker("vanilla"):
            item.add_marker(pytest.mark.pure)
    if getattr(config.option, "loadgroup", False):   # an xdist worker under --dist loadgroup: xdist 3.8 writes
        for item in items:                           # the group's suffix to _nodeid, which pytest 9.2 doesn't read
            if groups := sorted({str(m.args[0] if m.args else m.kwargs.get("name", "default"))
                                 for m in item.iter_markers("xdist_group")}):
                _ungrouped[grouped := f"{item.nodeid}@{'_'.join(groups)}"] = item.nodeid
                item._id = NodeId.parse(grouped)


def _stop(config, items, why: str) -> None:
    """Stop the run before any test with one message (D26). An xdist worker
    collects nothing and hands the message to the controller, which stops
    the run with it (:func:`pytest_testnodedown`)."""
    if hasattr(config, "workerinput"):
        config.workeroutput["stop"] = why
        items.clear()
    else:
        pytest.exit(why, returncode=pytest.ExitCode.USAGE_ERROR)


@pytest.hookimpl(tryfirst=True)   # after -m deselects; on an xdist worker before it sends its tests (D991)
def pytest_collection_finish(session):
    global _gated
    config, items = session.config, session.items
    needed = {release for item in items if item.get_closest_marker("vanilla")
              for release in ((gate.EUROPE,) if item.get_closest_marker("europe") else ())
              + ((gate.USA,) if "usa_iso" in getattr(item, "fixturenames", ()) or not item.get_closest_marker("europe") else ())}
    for release in sorted(needed, key=gate.RELEASES.index):
        found = _verify(release)
        if isinstance(found, str):
            return _stop(config, items, found)
        _images[release.name] = found
    uses = {name for item in items if item.get_closest_marker("web")
            for name in getattr(item, "fixturenames", ())}
    engines = {item.callspec.params["browser"] for item in items
               if "browser" in getattr(item, "fixturenames", ())}
    if uses & {"pyodide", "browser"}:
        if "pyodide" in uses and shutil.which("node") is None:
            return _stop(config, items, 'web tests need Node (24 or newer) on PATH, or run `pytest -m "not web"`')
        if lost := web_tools.missing(ROOT):
            return _stop(config, items, f"web tests need Pyodide {web_tools.VERSION} in {web_tools.pyodide_dir(ROOT)} "
                                        f"(it lacks {', '.join(lost)}): run `uv run bootstrap.py`, or "
                                        f'`pytest -m "not web"`')
        for engine in sorted(engines, key=list(web_tools.BROWSERS).index):
            if web_tools.browser_missing(engine, ROOT):
                return _stop(config, items, f"web tests need {web_tools.BROWSERS[engine][1]} in "
                                            f"{web_tools.browser_dir(engine, ROOT)}: run `uv run bootstrap.py`, or "
                                            f'`pytest -m "not web"`')
    _gated = True


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids):
    """Under xdist the workers collect and gate; the controller sums the tiers."""
    global _gated
    _gated = True


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    """A worker stopped at the gate stops the run with its message, as a run without xdist stops (D26)."""
    global _gated
    if why := getattr(node, "workeroutput", {}).get("stop"):
        _gated = False
        pytest.exit(why, returncode=pytest.ExitCode.USAGE_ERROR)


@pytest.fixture(scope="session")
def usa_iso() -> Path:
    """The verified USA image (the test is ``vanilla``)."""
    return _images["usa"]


@pytest.fixture(scope="session")
def europe_iso() -> Path:
    """The verified Europe image (the test is ``europe`` and ``vanilla``)."""
    return _images["europe"]


@pytest.fixture(scope="session")
def pyodide(tmp_path_factory) -> Callable[..., dict]:
    """``run(*argv)``: the ``azurkit`` command under Pyodide on Node, from
    this checkout's wheel alone (``tests/_pyodide.py``; the test is ``web``)."""
    wheel = web_tools.wheel(tmp_path_factory.mktemp("wheel"))
    return lambda *argv, **job: _pyodide.run(list(argv), wheel, **job)


@pytest.fixture(scope="module")
def browser(request, tmp_path_factory):
    """Each browser in turn, headless (Playwright's, from the main checkout's
    ``.tools/``; the test is ``web``): Chromium's headless shell, then
    WebKit, Safari's engine, then Firefox, or those ``--browsers`` names
    (:func:`pytest_generate_tests`). No window opens. Module-scoped, so a
    module's tests stay together and its other fixtures are made once."""
    from playwright.sync_api import sync_playwright
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("PLAYWRIGHT_BROWSERS_PATH", str(web_tools.browsers_dir(ROOT)))   # read as its driver starts
        with sync_playwright() as playwright:
            launched = getattr(playwright, request.param).launch(
                headless=True, downloads_path=str(tmp_path_factory.mktemp("downloads")))
            yield launched
            launched.close()


def _fail_unlisted_skip(report):
    """A skip or xfail the allow-list doesn't cover becomes a failure."""
    if report.skipped or hasattr(report, "wasxfail"):
        reason = (getattr(report, "wasxfail", "") or report.longrepr[2]).removeprefix("Skipped: ")
        allowed = ALLOWED_SKIPS.get(_ungrouped.get(report.nodeid, report.nodeid))
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
        for tier in ("vanilla", "europe", "web"):
            if tier in report.keywords:
                _ran[tier].add(report.nodeid)


def pytest_terminal_summary(terminalreporter):
    if _gated:
        terminalreporter.write_line(f"vanilla: {len(_ran['vanilla'])} run")
        terminalreporter.write_line(f"europe: {len(_ran['europe'])} run")
        terminalreporter.write_line(f"web: {len(_ran['web'])} run")

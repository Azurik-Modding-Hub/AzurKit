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
- A failed test runs once more at once; one that passes it is flaky, named
  in the summary and recorded, and the run passes; one that fails twice
  fails it (``tests/_rerun.py``, D1170).
- ``--shard=LABEL:K/N`` runs the K-th of N parts of the selected tests, cut
  by a runner's measured seconds with each ``xdist_group`` in one part
  (``scripts/ci_shards.py``: CI's vanilla tier, one job a part).
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
  doesn't hold. Every Firefox it launches takes no proxy (:data:`DIRECT`,
  under the launch's own prefs), so a request to a test's host never waits
  on the system's proxy settings, and on Windows' CI logs its requests,
  loads and hangs to a file (:data:`FIREFOX_LOG`), whose end a stalled call
  prints (``tests/_page.py``'s ``stalled``). Every Chromium it launches runs
  its GPU in the browser's own process (``scripts/web_tools.py``'s
  ``CHROMIUM``), so no macOS privacy prompt standing for another program
  holds a GPU helper of its apart.
- Git finds a repository by the cwd alone: the variables that point it at
  one (``GIT_DIR``, which ``git rebase -x`` exports, and the rest of ``git
  rev-parse --local-env-vars``) are dropped, so a test's scratch repo is its
  own.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import itertools
import os
import re
import shutil
import subprocess
import sys
import tempfile
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

#: The last: --shard (CI's vanilla tier); tests._rerun: a failed test's one rerun (D1170).
pytest_plugins = ["tests._byte_safe", "tests._rerun", "pytester", "scripts.ci_shards"]

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


DIRECT = {"network.proxy.type": 0}
"""The prefs under each Firefox the tests launch (a launch's own win): no proxy, so Firefox asks nothing before a
request to a test's host on 127.0.0.1. With Firefox's default, the system's settings (5), Playwright's
``network.proxy.allow_hijacking_localhost`` (its ``playwright.cfg``) keeps 127.0.0.1 in the proxy lookup and Juggler's
channel filter keeps every request off Firefox's direct fast path, so each request waits for the system's answer
before it starts (``nsHttpChannel``: its proxy, then ``http-on-modify-request``, Playwright's request event); on
Windows that answer is WinINet's, which can take seconds and more (Firefox's bug 1869403: "incredibly slow page load
with 'use system proxy' enabled without a system proxy"; its cache is dropped at each network or registry change). On
GitHub's Windows runner a page's first load of its host went unanswered 30 s in Firefox, its one request (``GET /``)
heard only 1 s before the failure, its host printing no error (run 42409729869): a request held before it started."""


def _direct(launch):
    """Playwright's ``launch``, a Firefox one's prefs over :data:`DIRECT`."""
    signature = inspect.signature(launch)

    @functools.wraps(launch)
    def direct(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        if getattr(bound.arguments["self"], "name", None) == "firefox":
            bound.arguments["firefoxUserPrefs"] = DIRECT | (bound.arguments.get("firefoxUserPrefs") or {})
        return launch(*bound.args, **bound.kwargs)
    return direct


def _chromium(launch):
    """Playwright's ``launch``, a Chromium one's arguments followed by those of :data:`web_tools.CHROMIUM` it lacks:
    its GPU in the browser's own process, which no privacy prompt standing for another program holds apart."""
    signature = inspect.signature(launch)

    @functools.wraps(launch)
    def chromium(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        if getattr(bound.arguments["self"], "name", None) == "chromium":
            given = list(bound.arguments.get("args") or ())
            bound.arguments["args"] = [*given, *(arg for arg in web_tools.CHROMIUM if arg not in given)]
        return launch(*bound.args, **bound.kwargs)
    return chromium


FIREFOX_LOG = "timestamp,sync,nsHttp:3,DocumentChannel:4,ProcessHangMonitor:4"
"""What each Firefox the tests launch on Windows' CI logs (Firefox's ``MOZ_LOG``), each to files of its own in this
process's folder (:func:`firefox_logs`), as it happens: its requests, its documents' loads and its hang monitor. On
GitHub's Windows runner Firefox held a page's first request about 37 s, its host never asked, the cause unshown (runs
42409729869 and 42494981621: PENDING 8.10); a stalled Firefox call prints the end of each of its newest files
(``tests/_page.py``'s ``stalled``)."""
FIREFOX_LOGS = sys.platform == "win32" and bool(os.environ.get("CI"))
"""Whether the Firefoxes the tests launch log so (:data:`FIREFOX_LOG`): on Windows' CI."""


def firefox_logs() -> Path:
    """The folder this process's Firefoxes log to (:data:`FIREFOX_LOG`), in the run's temporary folder (the runner's
    on CI)."""
    return Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / f"azurkit-firefox-log-{os.getpid()}"


_launches = itertools.count(1)


def _logged(launch):
    """Playwright's ``launch``, a Firefox one logging to a file of its own (``MOZ_LOG_FILE``, Firefox's processes'
    files beside it) where :data:`FIREFOX_LOGS`, under the environment the launch gives, else this process's."""
    signature = inspect.signature(launch)

    @functools.wraps(launch)
    def logged(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        if FIREFOX_LOGS and getattr(bound.arguments["self"], "name", None) == "firefox":
            (folder := firefox_logs()).mkdir(parents=True, exist_ok=True)
            bound.arguments["env"] = {**(bound.arguments.get("env") or os.environ), "MOZ_LOG": FIREFOX_LOG,
                                      "MOZ_LOG_FILE": str(folder / f"firefox-{next(_launches)}")}
        return launch(*bound.args, **bound.kwargs)
    return logged


for _name in ("launch", "launch_persistent_context"):   # the impl's: the sync and async APIs both call it
    setattr(_BrowserType, _name, _headless_only(_direct(_chromium(_logged(getattr(_BrowserType, _name))))))


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
            downloads = tmp_path_factory.mktemp("downloads")
            launched = getattr(playwright, request.param).launch(headless=True, downloads_path=str(downloads))
            yield launched
            close_browser(launched, downloads=downloads)


LEFT_S = 10
"""s a browser's close waits before the ``browser`` fixture ends what its ended browser left running (a close took at
most 0.5 s here, the browser's processes ending with it)."""
EVERY_S = 2
"""s between the fixture's looks for them while the close waits on."""


async def _closed(close, driver: int, seconds: float, ended: list) -> None:
    """Await ``close``, a browser's, in at most ``seconds`` s (past them TimeoutError, the close cancelled): once it
    has waited :data:`LEFT_S`, and every :data:`EVERY_S` after, end each browser's process a parent that ended left
    running since its driver (id ``driver``) began (``scripts/ci_resources.py``'s ``left``), each one's row added to
    ``ended``."""
    import asyncio

    from scripts import ci_resources
    loop = asyncio.get_running_loop()
    task, end = asyncio.ensure_future(close), loop.time() + seconds
    look = loop.time() + LEFT_S
    while not (await asyncio.wait({task}, timeout=max(0.0, (until := min(end, look)) - loop.time())))[0]:
        if until == end:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise TimeoutError
        ended.extend(await asyncio.to_thread(ci_resources.end_left, driver))
        look = loop.time() + EVERY_S
    task.result()


def close_browser(browser, seconds: float = 120, downloads: Path | None = None) -> None:
    """``browser.close()`` in at most ``seconds`` (``tests/_page.py``'s STALL, the bound a site test's call with none of
    its own has; a close took at most 0.5 s here). Playwright's driver answers a browser's close only once the
    browser's process has ended and every handle of its stdout, stderr and protocol pipes has closed, then removes its
    temporary folders (its ``launchProcess``), and its kill 30 s in, ``taskkill /T`` on Windows, reaches only the
    browser and the children of a live parent; Playwright's WebKit on Windows starts each of its processes with its own
    stdout and stderr and every handle it may pass on (its ``ProcessLauncherWin.cpp``). So a WebKitWebProcess.exe left
    by its ended browser held the close: on GitHub's Windows runner WebKit's close after the pack golden never
    answered (run 41779807138), and twice before the worker went silent there with its driver's browser gone and a
    WebKitWebProcess.exe left by its ended parent (runs 41744982709 and 182336a's), at the next item's setup, a Firefox
    one's. Once the close has waited :data:`LEFT_S`, what a parent that ended left running of the browsers' from
    Playwright's folders since the driver began is ended (:func:`_closed`), as the driver's kill would have had its
    parent lived, and a warning names each. Past ``seconds`` the close fails by name, saying whether the driver heard the browser's pipe close, what was
    ended and what it may wait on (``scripts/ci_resources.py``'s ``held``: the processes under the driver and those a
    parent that ended left running, with their memory, the crash handlers and the browser's temporary and
    ``downloads`` folders' sizes); the driver ends with the fixture's ``sync_playwright`` (its own 30 s after its pipe
    closes). A browser that stopped answering (its connection closed by ``tests/_page.py``'s ``stalled``) has its close
    return at once, so what a parent that ended left running is ended then, while its driver still runs (``left``
    reads the driver's age), before the driver's exit."""
    import warnings

    from scripts import ci_resources
    driver, name, ended = browser._impl_obj._connection._transport._proc.pid, browser.browser_type.name, []
    try:
        browser._sync(_closed(browser._impl_obj.close(), driver, seconds, ended))
    except TimeoutError:
        raise AssertionError("\n".join([
            f"no answer in {seconds:.0f} s: the {name} browser's close, its driver {driver}",
            f"its driver heard its browser's pipe close: {'no' if browser.is_connected() else 'yes'}",
            *([f"ended, left running by a parent that ended: {'; '.join(map(ci_resources.described, ended))}"]
              if ended else []),
            *ci_resources.held(driver, {"its downloads": downloads} if downloads else {})])) from None
    if stopped := _stopped(browser):
        ended.extend(ci_resources.end_left(driver))
    if ended:
        how = "on its closed connection found" if stopped else "waited on"
        warnings.warn(f"the {name} browser's close {how} what a parent that ended left running, out of its driver's "
                      f"kill's reach, ended: {'; '.join(map(ci_resources.described, ended))}", stacklevel=2)


def _stopped(launched) -> str:
    """Why ``launched``'s Playwright connection (a browser's) is closed (``tests/_page.py``'s ``stalled`` closes it,
    naming the call its browser left unanswered), or ``""`` while it's open. (Its parameter isn't named ``browser``:
    ``scripts/fullsuite.py``'s graph would read the fixture, and its close's imports, as every session's.)"""
    error = getattr(getattr(getattr(launched, "_impl_obj", None), "_connection", None), "_closed_error", None)
    return "" if error is None else str(error) or type(error).__name__


@pytest.hookimpl(tryfirst=True)   # before pytest's own setup makes the test's fixtures
def pytest_runtest_setup(item):
    """A module's ``browser`` that stopped answering is launched again for the next test that takes it, the stalled
    test's rerun too (D1260): ``tests/_page.py``'s ``stalled`` closes its Playwright connection naming the call, which
    fails its try by name (D1072), and every later call to it would fail at once; ``tests/_rerun.py``'s rerun makes
    again only a fixture whose setup raised, so the rerun and the module's later tests got that browser and each
    failed at once (CI run 43431651205's Windows WebKit tests). So the setup first finishes it, as its module's end
    would (its fixtures' teardowns, then :func:`close_browser`'s, then its driver's exit), and launches it again, a
    warning naming it; an error its teardown raises on the closed connection is said there, never this setup's."""
    import warnings

    request = getattr(item, "_request", None)
    for fixturedef in getattr(getattr(item, "_fixtureinfo", None), "name2fixturedefs", {}).get("browser", ()):
        cached = fixturedef.cached_result
        if request and cached is not None and cached[2] is None and (why := _stopped(cached[0])):
            try:
                fixturedef.finish(request)
            except Exception as error:
                why += f"; its teardown: {type(error).__name__}: {str(error)[:200]}"
            warnings.warn(f"the module's browser stopped answering ({why}): launched again", stacklevel=1)


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

"""The landing tools: ``scripts/fullsuite.py``'s changed-area plan,
``scripts/perf.py``'s verdicts and ``scripts/land.py``'s gate: a
fast-forward, a passing receipt and its perf block; the developer log's
union merge and its stale bullets (``scripts/devlog.py``)."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
import signal
import subprocess
import sys
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from scripts import devlog, flake_repeat, fullsuite, land, perf
from tests import _page, _perf

ROOT = Path(__file__).resolve().parent.parent
SMOKE = sorted(fullsuite.SMOKE)


def test_the_changed_area_plan_picks_importers_and_falls_back_to_the_whole_suite():
    """A changed module selects every test file that reaches it through
    imports; src/ adds the files that run the whole package (SRC_TESTS);
    docs select only the smoke files (the lint files and the gate's test,
    whose USA and Europe cases make every receipt run both tiers); the
    suite's configuration, what every session
    loads, an unknown path and a Python file outside graph()'s folders and the
    root (review S1: under web/ or .github/ too) make it whole. The session loads only
    what tests/conftest.py imports (it checks the app in a Python of its
    own), so here a change to the sdk is changed-area."""
    deps = {"azurkit": set(), "azurkit.core": {"azurkit"}, "azurkit.core.iso": {"azurkit", "azurkit.core"},
            "azurkit.core.gate": {"azurkit", "azurkit.core"},
            "azurkit.sdk": {"azurkit", "azurkit.core", "azurkit.core.iso"},
            "tests.conftest": {"azurkit", "azurkit.core", "azurkit.core.gate"},
            "tests.test_sdk": {"azurkit", "azurkit.sdk"}, "tests.test_gate": {"azurkit.core.iso"},
            "tests.test_wheel": {"azurkit"}, "tests.test_other": {"json"}, "bootstrap": set()}
    assert "tests/test_gate.py" in SMOKE
    assert any("pytest.mark.europe" in (ROOT / f.partition("::")[0]).read_text(encoding="utf-8") for f in SMOKE)  # D26
    assert fullsuite.plan(["src/azurkit/core/iso.py"], deps) == sorted(
        {*SMOKE, "tests/test_sdk.py", *fullsuite.SRC_TESTS})
    assert fullsuite.plan(["tests/test_other.py", "AGENTS.md", "tests/sdk_api.txt"], deps) == sorted(
        {*SMOKE, "tests/test_other.py"})
    assert fullsuite.plan(["bootstrap.py"], deps) == fullsuite.plan(["tests/perf_ceilings.toml"], deps) == SMOKE
    for whole in ("pyproject.toml", "uv.lock", "tests/conftest.py", "src/azurkit/core/gate.py", "assets/icon/a.icns",
                  "docs/gen.py", "web/serve.py", ".github/scripts/check.py"):
        assert fullsuite.plan([whole], deps) is None, whole
    assert fullsuite.plan(["src/azurkit/sdk.py"], fullsuite.graph(ROOT)) is not None


def test_a_dev_area_change_picks_its_importers_and_every_plan_lints_the_agent_files(tmp_path):
    """Step 4.11b: graph() reads devkit/, shimkit/ and nativekit/ as it reads
    src/, so a change to a dev module picks the test files reaching it through
    other dev modules, and a file under devkit/<area>/ that isn't Python or a
    doc is that package's (it reads its data by ``__file__``): it picks what
    reaches the package or a module outside it naming the file (bootstrap's
    tools pin, review F1), not the whole suite. Every plan holds the lint
    files, the agent files' among them: their scan of every tracked text
    file for a home path or an ``$EV`` cite reads whatever a change touches
    (a doc's, a workflow's, a kernel's or a comment's edit alone; Step
    4.4dx3's review F1), and a docs-only change edits the agent files. The
    modules here are made up: a real one's path in this file would make
    graph() read it as a program this file runs, and its changes pick this file."""
    files = {"devkit/lab/snapshot.py": "", "devkit/rig/queue.py": "from devkit.lab import snapshot\n",
             "devkit/area/__init__.py": "", "devkit/area/reader.py": "", "shimkit/probe.py": "",
             "nativekit/probe.py": "", "tests/test_rig.py": "from devkit.rig import queue\n",
             "tests/test_area.py": "from devkit.area import reader\n", "tests/test_other.py": "import json\n",
             "pins.py": 'TOOLS = "devkit/area/data/x.toml"\n', "tests/test_pins.py": "import pins\n"}
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    deps = fullsuite.graph(tmp_path)
    assert {"shimkit.probe", "nativekit.probe", "devkit.rig.queue"} <= deps.keys()
    assert "tests/test_agent_files.py" in fullsuite.LINT
    for changed, picks in ((["devkit/lab/snapshot.py"], {"tests/test_rig.py"}),
                           (["devkit/area/data/x.toml"], {"tests/test_area.py", "tests/test_pins.py"}),
                           (["AGENTS.md", "devkit/area/README.md"], set()),
                           ([".github/workflows/tests.yml", "native/reach.c"], set()), ([], set())):
        assert fullsuite.plan(changed, deps) == sorted({*SMOKE, *picks}), changed


def test_a_change_in_the_goldens_picks_the_test_files_that_read_them():
    """tests/goldens/ is read by path, not imported: a change in it picks
    each test file that reaches a module naming it
    (``scripts/record_goldens.py``'s GOLDENS), every family's (the packs',
    the characters', the randomizer's and its maps'), not the smoke files
    alone."""
    goldens = fullsuite.plan(["tests/goldens/rando_plans.json", "tests/goldens/probes.json"], fullsuite.graph(ROOT))
    assert {f"tests/test_{name}.py" for name in ("characters", "packs", "builds", "shims", "xbr", "fps_unlock",
                                                 "randomizer", "art", "hosts", "site")} <= set(goldens) - set(SMOKE)


def test_the_page_picks_the_site_app_and_icon_tests_and_the_docs_they_restate_pick_theirs():
    """D970: a change under web/ selects the site's, the app's and the
    favicons' test files; LICENSE and NOTICE.md the About tab's test (inside
    its file when that is picked whole) and the wheel's, README.md the
    wheel's, any other doc only the smoke files. Each rule names a test file
    and test that exist, and SRC_TESTS every test file whose tests run the
    package outside the import graph (the pyodide, browser and frozen_app
    fixtures) besides the wheel's."""
    deps = {"tests.test_site": {"json"}, "tests.test_hosts": {"json"}, "tests.test_wheel": {"json"}}
    page = ["tests/test_hosts.py", "tests/test_icon.py", "tests/test_service_worker.py", "tests/test_site.py"]
    assert fullsuite.plan(["web/app.mjs", "web/favicon.ico"], deps) == sorted({*SMOKE, *page})
    assert fullsuite.plan(["NOTICE.md"], deps) == sorted({*SMOKE, fullsuite.ABOUT, "tests/test_wheel.py"})
    assert fullsuite.plan(["LICENSE", "web/index.html"], deps) == sorted({*SMOKE, *page, "tests/test_wheel.py"})
    assert fullsuite.plan(["README.md", "AGENTS.md", "CLAUDE.md"], deps) == sorted({*SMOKE, "tests/test_wheel.py"})
    assert fullsuite.plan(["AGENTS.md", "docs/plan.md"], deps) == SMOKE
    for test in {test for _, tests in fullsuite.RULES for test in tests}:
        file, _, name = test.partition("::")
        assert f"\ndef {name}(" in (ROOT / file).read_text(encoding="utf-8") if name else (ROOT / file).is_file(), test
    runs = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py") if re.search(
        r"^def test_\w+\([^)]*\b(pyodide|browser|frozen_app)\b", p.read_text(encoding="utf-8"), re.M)}
    assert sorted({fullsuite.WHEEL, *runs}) == sorted(fullsuite.SRC_TESTS)


def test_a_shipped_picture_or_the_page_hasher_picks_the_test_that_checks_it_against_a_fresh_build():
    """Step 4.46a: a change to the Tracker's shipped maps, the Characters
    tab's shipped pictures or ``web/md5.wasm`` alone picks, beside the
    page's tests (every RULES row a path matches), the test that holds those
    files to what a fresh draw or ``nativekit`` makes of them, so a lane
    that re-records them alone is checked; any other page file only the
    page's."""
    deps = {"tests.test_site": {"json"}}
    page = ["tests/test_hosts.py", "tests/test_icon.py", "tests/test_service_worker.py", "tests/test_site.py"]
    for path, holder in (("web/art/1-x/w1.png", "tests/test_art.py::test_the_shipped_maps_are_what_the_tracker_draws"
                                               "_from_each_image"),
                         ("web/characters/index.json", "tests/test_characters.py::test_the_shipped_species_and_"
                                                       "pictures_are_what_each_image_gives"),
                         ("web/md5.wasm", "tests/test_native.py::test_nativekit_rebuilds_each_committed_library_"
                                          "to_its_bytes")):
        assert fullsuite.plan([path], deps) == sorted({*SMOKE, *page, holder}), path
    assert fullsuite.plan(["web/app.mjs"], deps) == sorted({*SMOKE, *page})


def test_what_every_session_runs_is_whole_and_what_only_a_fixture_runs_picks_its_takers():
    """Step 4.4dx3: a module conftest's hooks or top level reach, through any
    function they name however deep, is the whole suite, as is a change to
    conftest's top level or a hook of it; one only a conftest fixture's body
    runs (its own function or a module it imports) picks the test files that
    take the fixture (or a helper of theirs does, or they compute its name); a
    module's unused function or its ``__main__`` block isn't the session's; a
    module run by its path is used by the one that names it; a relative import
    is an import. A path holding "::" is a part only when it names a function
    of a module every session runs; else it is the whole suite."""
    files = {"tests/conftest.py": "import pytest\nfrom scripts import tools\n\n\ndef pytest_sessionstart(session):\n"
                                  "    tools.check()\n\n\n@pytest.fixture\ndef page():\n    return _open()\n\n\n"
                                  "def _open():\n    from scripts import pages\n    return pages\n",
             "scripts/tools.py": "def check():\n    from scripts import hooked\n\n\ndef unused():\n"
                                 "    from scripts import lazy\n\n\nif __name__ == '__main__':\n    unused()\n",
             "scripts/hooked.py": "", "scripts/lazy.py": "", "scripts/pages.py": "import scripts.deep\n",
             "scripts/deep.py": "", "tests/_server.py": "", "src/pkg/core.py": "",
             "tests/_helper.py": "import pytest\n\n\n@pytest.fixture\ndef wrapped(page):\n    return page\n",
             "tests/_runner.py": "from pathlib import Path\n\nSERVER = Path(__file__).with_name('_server.py')\n",
             "src/pkg/__init__.py": "from . import core\n",
             "tests/test_takes.py": "def test_a(page):\n    pass\n",
             "tests/test_wraps.py": "from tests._helper import wrapped  # noqa: F401\n",
             "tests/test_computes.py": "def test_c(request, kind):\n    request.getfixturevalue(f'{kind}age')\n",
             "tests/test_iso.py": "def test_d(request, kind):\n    request.getfixturevalue(f'{kind}_iso')\n",
             "tests/test_lazy.py": "from scripts import lazy  # noqa: F401\n",
             "tests/test_serves.py": "from tests import _runner  # noqa: F401\n", "tests/test_pkg.py": "import pkg\n"}
    deps = fullsuite.graph_of(files)
    conftest = files["tests/conftest.py"]
    assert [fullsuite.parts("tests/conftest.py", conftest, conftest.replace(*edit)) for edit in (
        ("return pages", "return pages.deep"), ("import pytest\n", "import pytest\nimport os\n"),
        ("import pytest", '"""a docstring"""\nimport pytest'))] == [["tests/conftest.py::_open"], ["tests/conftest.py"], []]
    for whole in ("tests/conftest.py", "tests/conftest.py::pytest_sessionstart", "scripts/tools.py", "scripts/hooked.py",
                  "scripts/tools.py::check", "scripts/lazy.py::unused", "tests/cases::x.json", "tests/conftest.py::"):
        assert fullsuite.plan([whole], deps) is None, whole   # a "::" in a path's own name: review S2
    takers = {*SMOKE, "tests/test_takes.py", "tests/test_wraps.py", "tests/test_computes.py"}
    assert fullsuite.plan(["tests/conftest.py::_open"], deps) == sorted(takers)
    assert fullsuite.plan(["scripts/tools.py::unused"], deps) == SMOKE
    picks = {rel: fullsuite.plan([rel], deps) for rel in ("scripts/lazy.py", "scripts/deep.py", "tests/_server.py",
                                                         "src/pkg/core.py")}
    assert picks == {"scripts/lazy.py": sorted({*SMOKE, "tests/test_lazy.py"}),
                     "scripts/deep.py": sorted(takers),
                     "tests/_server.py": sorted({*SMOKE, "tests/test_serves.py"}),
                     "src/pkg/core.py": sorted({*SMOKE, *fullsuite.SRC_TESTS, "tests/test_pkg.py"})}


def test_a_deleted_or_renamed_module_picks_the_tests_that_still_name_it_and_one_none_names_is_the_whole_suite(
        tmp_path, monkeypatch):
    """Step 4.4dx3, second review D1: a deleted module run by its path
    (``tests/_page.py`` runs ``tests/_static.py``) still picks the test files
    that reach the one naming it, and an imported one its importers; a
    deleted module no module names is the whole suite (who ran it isn't in
    the head tree), a deleted test file only the smoke files. A rename is its
    old path deleted and its new one added."""
    deps = fullsuite.graph_of({"tests/_runner.py": "from pathlib import Path\n\nS = Path(__file__).with_name('_x.py')\n",
                               "tests/test_serves.py": "from tests import _runner  # noqa: F401\n"})
    assert fullsuite.plan(["tests/_x.py"], deps) == sorted({*SMOKE, "tests/test_serves.py"})
    assert fullsuite.plan(["tests/_gone.py"], deps) is None
    assert fullsuite.plan(["tests/test_gone.py"], deps) == SMOKE
    _, lane, _, _ = _repo(tmp_path, monkeypatch)
    (lane / "tests").mkdir()
    (lane / "tests" / "_old.py").write_text("", encoding="utf-8")
    (lane / "tests" / "test_a.py").write_text("from tests import _old  # noqa: F401\n", encoding="utf-8")
    _git(lane, "add", "tests")
    _git(lane, "commit", "-q", "-m", "base")
    base = _git(lane, "rev-parse", "HEAD")
    _git(lane, "mv", "tests/_old.py", "tests/_new.py")
    _git(lane, "commit", "-q", "-m", "renamed")
    assert "tests/test_a.py" in fullsuite.prepare(lane, True, base)["pytest_args"]


def test_a_file_that_isnt_python_picks_the_test_files_that_name_it_and_one_none_names_is_the_whole_suite():
    """Step 4.4dx11: a file no rule covers that isn't Python (a shell
    script, ``.gitattributes``, a package's data) picks the test files
    reaching a module whose strings hold its name as a word, a docstring's
    aside (here ``scripts/ci_retry.sh`` picks test_contracts, which reads
    it), and below the top level one naming its folder or sitting in it
    (a package reads its data by ``__file__``); deleted, its users still
    name it. One no module names, or one a module every session runs
    names, stays the whole suite."""
    files = {"tests/conftest.py": "TIMES = 'tests/durations.json'\n",
             "tests/test_reads.py": "from pathlib import Path\n\nRETRY = Path('scripts') / 'retry.sh'\n"
                                    "OLD = '. gone.sh'\n",
             "tests/test_told.py": '"""It reads scripts/told.sh."""\n\nNAME = "told.shx"\n',
             "scripts/tools.py": "", "tests/test_tools.py": "from scripts import tools  # noqa: F401\n",
             "src/pkg/__init__.py": "", "src/other.py": "",
             "src/pkg/loader.py": "from pathlib import Path\n\nKITS = Path(__file__).parent / 'kits'\n", "tests/test_pkg.py": "from pkg import loader  # noqa: F401\n",
             "tests/test_other.py": "import other  # noqa: F401\n"}
    deps = fullsuite.graph_of(files)
    reads, pkg = sorted({*SMOKE, "tests/test_reads.py"}), sorted({*SMOKE, *fullsuite.SRC_TESTS, "tests/test_pkg.py"})
    assert {rel: fullsuite.plan([rel], deps) for rel in (
        "scripts/retry.sh", "scripts/gone.sh", "src/pkg/table.json", "src/pkg/kits/a.glb", "scripts/told.sh",
        "tests/durations.json", "scripts/new.sh")} == {
        "scripts/retry.sh": reads, "scripts/gone.sh": reads, "src/pkg/table.json": pkg, "src/pkg/kits/a.glb": pkg,
        "scripts/told.sh": None, "tests/durations.json": None, "scripts/new.sh": None}
    checkout = fullsuite.graph(ROOT)
    assert "tests/test_contracts.py" in (fullsuite.plan(["scripts/ci_retry.sh"], checkout) or [])
    assert "tests/test_dev_tools.py" in (fullsuite.plan([".gitattributes"], checkout) or [])
    assert fullsuite.plan(["tests/ci_durations.json"], checkout) is None   # scripts/ci_shards.py, every session's


def test_a_change_to_a_functions_decorators_or_defaults_is_its_modules_top_level():
    """Step 4.4dx3, review F2: a function's decorators and defaults run as its
    module loads, so a change to them is its module's (conftest's: the whole
    suite): a fixture whose ``autouse`` goes ran for every test, not only for
    those the head tree finds taking it; so is a default computed, or a
    function added with a decorator. A literal default runs nothing: a change
    to one, or a function added with one, is a part of its own."""
    base = "import pytest\n\n\n@pytest.fixture(autouse=True)\ndef guard():\n    pass\n\n\ndef helper(n=1):\n    return n\n"
    for new in (base.replace("(autouse=True)", ""), base.replace("n=1", "n=int('2')"),
                base + "\n\n@pytest.fixture\ndef more():\n    pass\n"):
        changed = fullsuite.parts("tests/conftest.py", base, new)
        deps = fullsuite.graph_of({"tests/conftest.py": new, "tests/test_a.py": "def test_a():\n    pass\n"})
        assert changed == ["tests/conftest.py"] and fullsuite.plan(changed, deps) is None, new
    assert fullsuite.parts("tests/conftest.py", base, base.replace("n=1", "n=-2") + "\n\ndef bare(s=120.0):\n    pass\n"
                           ) == ["tests/conftest.py::bare", "tests/conftest.py::helper"]


def _users(*names: str) -> set[str]:
    """The test files whose import lines reach one of ``names`` (``tests._page``, ``scripts.perf``), directly or
    through tests/, scripts/ and devkit/ modules (``devkit.re.test_for_va`` runs fullsuite), or that run one by its
    file name beside them: read from the sources by pattern, apart from fullsuite.graph()."""
    def names_in(s: str) -> list[str]:
        return [n.split(" as ")[0].strip() for n in s.strip("()").split(",") if n.strip()]

    uses = {}
    for p in [*(ROOT / "tests").glob("*.py"), *(ROOT / "scripts").glob("*.py"), *(ROOT / "devkit").rglob("*.py")]:
        text, parts = p.read_text(encoding="utf-8"), p.relative_to(ROOT).with_suffix("").parts
        mod = ".".join(parts[:-1] if p.name == "__init__.py" else parts)
        pkg = mod if p.name == "__init__.py" else mod.rpartition(".")[0]
        found = {f"{m[0]}.{n}" for m in re.findall(r"^\s*from ((?:tests|scripts|devkit)(?:\.\w+)*) import "
                                                   r"(\([^)]*\)|[^\n#]+)", text, re.M) for n in names_in(m[1])}
        found |= set(re.findall(r"^\s*(?:from|import) ((?:tests|scripts|devkit)(?:\.\w+)+)", text, re.M))
        found |= {f"{pkg}.{n}" for n in re.findall(r"^\s*import (\w+)", text, re.M)}   # a sibling on sys.path (perf)
        for dots, sub, what in re.findall(r"^\s*from (\.+)([\w.]*) import (\([^)]*\)|[^\n#]+)", text, re.M):
            base = ".".join([*pkg.split(".")[:len(pkg.split(".")) - len(dots) + 1], *filter(None, [sub])])
            found |= {base, *(f"{base}.{n}" for n in names_in(what))}
        uses[mod] = found | {f"{pkg}.{n}" for n in re.findall(r"with_name\(\"(\w+)\.py\"\)", text)}
    reached, more = set(names), set(names)
    while more := {m for m, found in uses.items() if m not in reached and found & more}:
        reached |= more
    return {f"tests/{m.removeprefix('tests.')}.py" for m in reached if m.startswith("tests.test_")}


def test_each_test_helper_picks_the_test_files_its_imports_reach_and_only_what_every_session_loads_is_whole():
    """Step 4.4dx3, on this checkout: each tests/ helper picks the smoke files
    and the test files whose imports reach it (:func:`_users`, read apart from
    graph()), not the whole suite, unless conftest loads it at its top or as a
    plugin; ``scripts/ci_resources.py``, which conftest runs only in the
    browser fixture's close, picks the browser tests and its importers' too;
    the workflows their readers; what conftest, its plugins and their tops
    reach is whole; every tracked Python file is in the graph."""
    deps = fullsuite.graph(ROOT)
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    loaded = {f"tests/{n}.py" for n in re.findall(r"^from tests import (\w+)", conftest, re.M)
              + re.findall(r"\"tests\.(\w+)\"", re.search(r"^pytest_plugins = .*$", conftest, re.M)[0])}
    assert loaded == {"tests/_pyodide.py", "tests/_byte_safe.py", "tests/_rerun.py"}
    for helper in sorted({f"tests/{p.name}" for p in (ROOT / "tests").glob("_*.py")} - {"tests/__init__.py"}):
        want = None if helper in loaded else sorted({*SMOKE, *_users(fullsuite.module_of(helper))})
        assert fullsuite.plan([helper], deps) == want, helper
    takers = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py") if re.search(
        r"^def test_\w+\([^)]*\bbrowser\b", p.read_text(encoding="utf-8"), re.M)}
    assert fullsuite.plan(["scripts/ci_resources.py"], deps) == sorted(
        {*SMOKE, *takers, *_users("scripts.ci_resources", "tests._page")})
    readers = {f"tests/{p.name}" for p in (ROOT / "tests").glob("test_*.py")
               if re.search(r'/ "\.github" /', p.read_text(encoding="utf-8"))}
    assert fullsuite.plan([".github/workflows/tests.yml"], deps) == sorted({*SMOKE, *readers})
    for whole in ("tests/conftest.py", "scripts/web_tools.py", "scripts/ci_shards.py", "src/azurkit/core/gate.py"):
        assert fullsuite.plan([whole], deps) is None, whole
    assert fullsuite.plan(["src/azurkit/tools/characters/__init__.py"], deps) is not None   # web_tools' lazy import
    assert not {fullsuite.module_of(rel) for rel in _git(ROOT, "ls-files", "*.py").split()} - deps.keys()


def test_a_changed_area_run_drives_the_page_in_chromium_alone_and_a_whole_run_in_every_browser(
        tmp_path, monkeypatch, pytester):
    """D970: a changed-area run's receipt names Chromium and its pytest
    command asks for it alone (``--browsers``), keyed so a receipt for other
    browsers is another; a whole run's names every browser and asks for no
    narrowing. The ``browser`` fixture runs a test in each browser it is
    given, every one by default."""
    _, lane, _, _ = _repo(tmp_path, monkeypatch)
    (lane / "README.md").write_text("a doc\n", encoding="utf-8")
    _git(lane, "add", "README.md")
    _git(lane, "commit", "-q", "-m", "a doc")
    changed, whole = fullsuite.prepare(lane, True, "main"), fullsuite.prepare(lane, False, "main")
    assert (changed["mode"], changed["browsers"], whole["mode"], whole["browsers"]) == (
        "changed", ["chromium"], "full", "all")
    asks = {run: [a for a in fullsuite.command(m) if a.startswith("--browsers")]
            for run, m in (("changed", changed), ("whole", whole))}
    assert asks == {"changed": ["--browsers=chromium"], "whole": []}
    assert all({f"--numprocesses={fullsuite.WORKERS}", "--dist=loadgroup"} <= set(fullsuite.command(m))
               for m in (changed, whole))   # D991: every run on xdist's workers, a group on one
    monkeypatch.setattr(fullsuite, "CHANGED_BROWSERS", ("webkit",))
    assert fullsuite.prepare(lane, True, "main")["key"] != changed["key"]
    pytester.makeconftest("from tests.conftest import *  # noqa: F403\n\n\n"
                          "def pytest_deselected(items):\n    print('ran in', *(item.nodeid for item in items))\n")
    pytester.makepyfile(test_x="def test_page(browser):\n    pass\n")
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    for run, ids in (("changed", "[chromium]"),
                     ("whole", "[chromium] test_x.py::test_page[webkit] test_x.py::test_page[firefox]")):
        done = pytester.runpytest_subprocess("-p", "no:cacheprovider", "-s", "--collect-only", "-m", "not web",
                                             *asks[run])   # collected and deselected: no browser starts
        assert f"ran in test_x.py::test_page{ids}\n" in done.stdout.str(), run


def test_the_cap_scales_with_the_load_per_cpu_up_to_twice():
    """A run's cap is CAP while the host's 5-minute load is at most one per
    CPU, then grows with it, up to twice CAP (Step 4.1g2)."""
    assert [fullsuite.cap(load5, 24) for load5 in (0, 24, 36, 48, 96)] == [1800, 1800, 2700, 3600, 3600]


def test_a_queued_run_takes_the_suite_lock_only_on_its_turn_and_never_waits_in_flocks_line(tmp_path, monkeypatch):
    """D1222: macOS hands a released flock to its first waiter in the order
    they blocked, so a run waiting in flock's line passed every later taker,
    a seat's window too. A queued run tries the lock (each try LOCK_NB,
    POLL apart) and takes it on its turn: no older queued run waits for it (a
    stopped runner, or a stale meta whose pid another process took, holds
    none back), and no seat's window waits for it (``lock.window``: a pid
    that lives, rewritten in the last FRESH seconds) while a run took it last
    (``lock.turn``, or a run that started since, as an older lane's, which
    writes none). The run that takes it writes ``gate <key>``. Processes,
    the window and the flock are stand-ins."""
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    procs, live = {}, {4242}
    monkeypatch.setattr(fullsuite, "processes", lambda pids: {p: procs[p] for p in pids if p in procs})
    monkeypatch.setattr(fullsuite, "alive", lambda pid: pid in live)

    def queued(name, second, pid):
        meta = receipts / f"suite-{name}.meta"
        fullsuite.save(meta, {"key": name, "state": "queued", "queued_at": f"2026-11-11T08:00:{second:02d}-08:00",
                              "runner_pid": pid})
        procs[pid] = ("S", f"python scripts/fullsuite.py --run {meta}")
        return meta, fullsuite.load(meta)

    g1, g2 = queued("g1", 1, 101), queued("g2", 2, 102)
    turn, wants, turns = (lambda g: fullsuite.turn(*g)), receipts / "lock.window", receipts / "lock.turn"
    assert (turn(g1), turn(g2)) == (True, False)   # the older first
    for other in (("T", procs[101][1]), ("S", "sleep 60")):   # stopped; its pid another process's
        procs[101] = other
        assert turn(g2), other
    procs[101] = ("S", f"python scripts/fullsuite.py --run {g1[0]}")
    wants.write_text("window 7 pid 4242\n", encoding="utf-8")
    seen = {}
    for took in ("gate g0", "window 7"):
        turns.write_text(took + "\n", encoding="utf-8")
        seen[took] = (fullsuite.last(receipts), turn(g1))
    old = time.time() - 60
    os.utime(turns, (old, old))
    fullsuite.save(receipts / "suite-old.meta", {"key": "old", "state": "done", "started_at": fullsuite.now()})
    seen["an older lane's run since"] = (fullsuite.last(receipts), turn(g1))
    os.utime(wants, (old, old))
    seen["the window's wait not rewritten"] = (fullsuite.last(receipts), turn(g1))
    assert seen == {"gate g0": ("gate", False), "window 7": ("window", True), "an older lane's run since":
                    ("gate", False), "the window's wait not rewritten": ("gate", True)}

    for g in (g1, g2):
        fullsuite.save(g[0], g[1] | {"state": "done"})
    meta = receipts / "suite-r.meta"
    m = fullsuite.prepare(lane, True, base) | {"state": "queued", "queued_at": fullsuite.now(), "runner_pid": os.getpid()}
    fullsuite.save(meta, m)
    ops, naps, ran = [], [], []

    def flock(fd, op):   # held by another for the first two tries
        ops.append(op)
        if op != 8 and sum(o != 8 for o in ops) <= 2:
            raise BlockingIOError

    monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8, flock=flock))
    monkeypatch.setattr(fullsuite.time, "sleep", naps.append)
    monkeypatch.setattr(fullsuite, "run", lambda meta, m: ran.append(meta.stem))
    assert fullsuite.runner(meta) == 0
    assert (ran, naps, turns.read_text(encoding="utf-8")) == (["suite-r"], [fullsuite.POLL] * 2, f"gate {m['key']}\n")
    assert ops and all(op & 4 for op in ops if op != 8), ops   # every take a try: none waits in flock's line


def test_a_queued_run_whose_worktree_moves_before_it_gets_the_lock_ends_stale_runs_no_pytest_and_lands_nothing(
        tmp_path, monkeypatch):
    """A run checks its worktree's HEAD and tree (``fullsuite.snapshot``)
    again once the lock comes: one that held runs; one the landing queue
    rebased, or one edited, while it waited ends "stale" with no pytest,
    status 1 (the queue runs it again), its note naming its command, and land
    takes nothing from it (Step 4.43a). The lock is a stand-in that moves the
    tree as the run waits on it, so a check before the wait would miss it."""
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    _git(lane, "commit", "-q", "--allow-empty", "-m", "b")
    ran = []
    monkeypatch.setattr(fullsuite, "run", lambda meta, m: ran.append(meta.stem))
    moves = {"held": lambda: None, "rebased": lambda: _git(lane, "commit", "-q", "--allow-empty", "-m", "c"),
             "edited": lambda: (lane / "x.txt").write_text("x", encoding="utf-8")}
    for name, move in moves.items():
        meta = receipts / f"suite-{name}.meta"
        fullsuite.save(meta, fullsuite.prepare(lane, True, base) | {"state": "queued", "runner_pid": os.getpid()})
        lock = types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8,   # moved as the run tries it
                                     flock=lambda fd, op, move=move: move())
        monkeypatch.setitem(sys.modules, "fcntl", lock)
        assert fullsuite.runner(meta) == 0
        if name != "held":
            m = fullsuite.load(meta)
            assert (m["state"], fullsuite.status_code(m)) == ("stale", 1), name
            assert m["note"].endswith(f"no pytest ran; run it again: scripts/fullsuite.py {lane} --changed --base {base}")
    assert ran == ["suite-held"]
    assert land.land(repo, "p2/x")[0] == 1   # the edited one's head is the branch's: stale, it lands nothing


def test_the_flake_stage_takes_the_tests_a_stack_added_or_edited_and_only_in_a_changed_run(tmp_path, monkeypatch):
    """A changed-area run's flake stage takes each test function the stack
    adds or edits against its base (a new or renamed one, an edited body or
    decorator; committed, or in an untracked file), not one left word for
    word (moved, or beside an edited helper), a helper file's or a deleted
    file's; a whole run has none (Step 4.4dx2)."""
    _, lane, _, _ = _repo(tmp_path, monkeypatch)
    tests = lane / "tests"
    tests.mkdir()
    kept, marked = "def test_kept():\n    assert helper()\n", "@pytest.mark.parametrize('x', [1])\ndef test_marked(x):"
    (tests / "test_a.py").write_text(f"import pytest\n\n\ndef helper():\n    return 1\n\n\n{kept}\n\ndef test_body():"
                                     "\n    assert 1\n\n\ndef test_marked():\n    pass\n\n\ndef test_renamed():\n"
                                     "    pass\n", encoding="utf-8")
    for name in ("_help.py", "test_gone.py"):
        (tests / name).write_text("def test_like():\n    pass\n", encoding="utf-8")
    _git(lane, "add", "tests")
    _git(lane, "commit", "-q", "-m", "base")
    base = _git(lane, "rev-parse", "HEAD")
    (tests / "test_a.py").write_text(f"import pytest\n\n\ndef helper():\n    return 2\n\n\ndef test_body():\n    assert 2"
                                     f"\n\n\n{marked}\n    pass\n\n\ndef test_other():\n    pass\n\n\n{kept}",
                                     encoding="utf-8")
    (tests / "_help.py").write_text("def test_like():\n    assert 1\n", encoding="utf-8")
    _git(lane, "rm", "-q", "tests/test_gone.py")
    _git(lane, "commit", "-q", "-am", "edits")
    (tests / "test_b.py").write_text("def test_new():\n    pass\n", encoding="utf-8")
    changed, whole = fullsuite.prepare(lane, True, base), fullsuite.prepare(lane, False, base)
    assert (changed["mode"], changed["flake_tests"]) == ("changed", [f"tests/test_a.py::test_{name}" for name in (
        "body", "marked", "other")] + ["tests/test_b.py::test_new"])
    assert (whole["mode"], whole["flake_tests"]) == ("full", [])


def test_the_flake_stage_fails_a_test_that_fails_one_run_in_three_by_name_and_passes_a_steady_one(tmp_path,
                                                                                                  monkeypatch):
    """Once the selected tests pass, the flake stage runs the tests a stack
    added or edited FLAKE_RUNS times slowed on FLAKE_WORKERS: on macOS
    under ``taskpolicy -b`` and nice 19 beside FLAKE_LOOPS at nice 10 if a
    probe under it ends within FLAKE_QUIET (a busy box starves it), else
    under the utility clamp beside FLAKE_UTILITY_LOOPS of its class;
    elsewhere under nice 19. A test that fails one run in three (one that
    takes a module-scoped fixture, here a stand-in browser: a session a run) fails the
    receipt at its third run by its name with its output's tail, and no
    perf stage runs; a steady one passes every run. The receipt keeps the
    stage: its tests, runs, and each run's wall time and slowing."""
    options, utility = fullsuite.slowings(), ["taskpolicy", "-c", "utility", *fullsuite.niced(19)]
    assert options == ([(["taskpolicy", "-b", *fullsuite.niced(19)], fullsuite.niced(10), fullsuite.FLAKE_LOOPS),
                        (utility, utility, fullsuite.FLAKE_UTILITY_LOOPS)] if sys.platform == "darwin" else
                       [(fullsuite.niced(19), fullsuite.niced(10), fullsuite.FLAKE_LOOPS)])
    monkeypatch.setattr(fullsuite, "FLAKE_QUIET", 0.001)   # a busy box: no probe ends in time
    assert fullsuite.slowed() == (options[-1], {" ".join(option[0]): None for option in options[:-1]})
    monkeypatch.setattr(fullsuite, "FLAKE_QUIET", 60)
    monkeypatch.setattr(fullsuite, "PROBE", "pass")
    option, probes = fullsuite.slowed()
    assert option == options[0] and list(probes) == [" ".join(o[0]) for o in options[:-1]][:1] and all(probes.values())
    assert fullsuite.flake_command(["t"], [])[-3:] == ["-rfE", f"--numprocesses={fullsuite.FLAKE_WORKERS}",
                                                       "--dist=loadgroup"]   # no --browsers
    monkeypatch.setattr(fullsuite, "slowed", lambda: ((fullsuite.niced(19), fullsuite.niced(10), 1), {}))
    monkeypatch.setattr(fullsuite, "PYTEST", (sys.executable, "-m", "pytest", "-p", "no:cacheprovider"))
    monkeypatch.setattr(fullsuite, "FLAKE_WORKERS", 0)   # in the run's own process: xdist's start is most of a run
    monkeypatch.setenv("PYTHONPATH", str(ROOT))   # the repeats' plugin (fullsuite.REPEAT)
    monkeypatch.setattr(fullsuite, "perf_stage", lambda meta, m: pytest.fail("a perf stage after a failed flake stage"))
    (tmp_path / "test_x.py").write_text(
        "from pathlib import Path\n\nimport pytest\n\nRUNS = Path(__file__).with_name('runs')\n\n\n"
        "@pytest.fixture(scope='module')\ndef browser():\n    return None\n\n\ndef test_flaky(browser):\n"
        "    RUNS.write_text(str(n := int(RUNS.read_text() if RUNS.exists() else 0) + 1))\n"
        "    assert n % 3, f'run {n} of the flaky test fails'\n\n\ndef test_steady():\n    pass\n", encoding="utf-8")
    meta = tmp_path / "suite-k.meta"
    m = fullsuite.stages(meta, {"key": "k", "subject": "s", "mode": "changed", "worktree": str(tmp_path), "cap_s": 600,
                                "pytest_args": [], "perf_args": ["--select", "a"], "state": "running", "exit_code": 0,
                                "flake_tests": ["test_x.py::test_flaky", "test_x.py::test_steady"]})
    flake = m["flake"]
    assert fullsuite.load(meta)["state"] == "flake"   # saved as it ran
    assert (flake["passed"], flake["runs"], flake["done"], len(flake["walls"])) == (False, fullsuite.FLAKE_RUNS, 3, 3)
    assert flake["tests"] == m["flake_tests"] and flake["wall_s"] > 0 and "perf" not in m
    assert [(f["test"], f["run"]) for f in flake["failures"]] == [("test_x.py::test_flaky", 3)]
    assert "run 3 of the flaky test fails" in "\n".join(flake["failures"][0]["tail"])
    done = m | {"state": "done"}
    assert fullsuite.status_code(done) == 1
    assert "test_x.py::test_flaky failed in run 3" in fullsuite.describe(done, meta)
    steady = fullsuite.flake_stage(meta, m | {"flake_tests": ["test_x.py::test_steady"]})
    assert (steady["passed"], steady["done"], steady["failures"]) == (True, fullsuite.FLAKE_RUNS, [])


def _quick_flake(monkeypatch) -> None:
    """The flake stage's runs in their pytest's own process (xdist's start is most of a run), slowed by nice alone,
    with this checkout's repeats plugin on their path (``fullsuite.REPEAT``)."""
    monkeypatch.setattr(fullsuite, "slowed", lambda: ((fullsuite.niced(19), fullsuite.niced(10), 0), {}))
    monkeypatch.setattr(fullsuite, "PYTEST", (sys.executable, "-m", "pytest", "-p", "no:cacheprovider"))
    monkeypatch.setattr(fullsuite, "FLAKE_WORKERS", 0)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))


def test_the_flake_stage_builds_nothing_again_that_the_gates_run_built(tmp_path, monkeypatch):
    """The gate's run and its flake stage share one build cache
    (``web_tools.kept``, ``<meta>.cache``): a stand-in for the site's wheel
    and database, built by a session fixture through it, is built once
    across the gate's run and the stage's five, never again slowed (an
    unshared one took more than 900 s under ``taskpolicy -b`` at load 50, so
    every case errored at setup, Step 4.4dx4); the cache goes with the run."""
    _quick_flake(monkeypatch)
    monkeypatch.setattr(fullsuite, "WORKERS", 0)
    monkeypatch.setenv("PYTHONPATH", str(ROOT))
    (tmp_path / "conftest.py").write_text(
        "from pathlib import Path\n\nimport pytest\n\nfrom scripts import web_tools\n\nBUILDS = Path(__file__).with_name("
        "'builds')\n\n\ndef build(out):\n    BUILDS.write_text(str(int(BUILDS.read_text() if BUILDS.exists() else 0) + 1))"
        "\n    out.mkdir(parents=True, exist_ok=True)\n    (made := out / 'wheel.whl').write_bytes(b'built')\n    return made"
        "\n\n\n@pytest.fixture(scope='session')\ndef wheel(tmp_path_factory):\n    return web_tools.kept('wheel', 'k', "
        "tmp_path_factory.mktemp('wheel'), build)\n", encoding="utf-8")
    (tmp_path / "test_x.py").write_text("def test_site(wheel):\n    assert wheel.read_bytes() == b'built'\n",
                                        encoding="utf-8")
    meta = tmp_path / "suite-k.meta"
    m = fullsuite.run(meta, {"key": "k", "subject": "s", "mode": "changed", "worktree": str(tmp_path), "browsers": "all",
                             "pytest_args": ["test_x.py"], "perf_args": [], "flake_tests": ["test_x.py::test_site"]})
    assert (m["state"], m["exit_code"], m["flake"]["passed"], m["flake"]["done"]) == ("done", 0, True, fullsuite.FLAKE_RUNS)
    assert (tmp_path / "builds").read_text() == "1" and not meta.with_suffix(".cache").exists()


def test_a_flake_run_or_collection_past_the_stages_cap_is_ended_with_its_processes_and_fails_the_stage_by_name(
        tmp_path, monkeypatch):
    """The stage's wall is FLAKE_CAP: a run still going at it is ended with
    every process under it (here a child in a session of its own, as
    Playwright starts a browser), each case it failed so far fails the
    stage, though it passed an earlier run (the slowest run is the one the
    cap ends), and each case that never passed fails it by name as capped,
    never a silent pass; a case that passed before the cap isn't named. The
    receipt keeps each run's wall time, within the stage's, which reaches the
    cap (no bound above either: a slow box's starts, kill and reap add to
    both). A collection still going at it is ended with its processes too (a
    child in its session, as ``uv run`` starts pytest) and fails the stage.
    Each stage then deletes its run's output, which no process of an ended
    run still holds (on Windows, where a held file can't be deleted, the end
    waits for each). The three stages run side by side."""
    _quick_flake(monkeypatch)
    monkeypatch.setattr(fullsuite, "FLAKE_CAP", 15)

    def stage(name: str, source: str, tests: list[str]) -> tuple[dict, Path]:
        (folder := tmp_path / name).mkdir()
        (folder / "test_x.py").write_text(source, encoding="utf-8")
        return fullsuite.flake_stage(meta := folder / "suite-k.meta", {"key": "k", "worktree": str(folder), "cap_s": 600,
                                                                     "flake_tests": tests}), meta

    with ThreadPoolExecutor() as pool:
        hung = pool.submit(stage, "hung", (   # ids with spaces, as a parameter's may hold
            "import subprocess, sys, time\nfrom pathlib import Path\n\nimport pytest\n\n\n@pytest.mark.parametrize('x', "
            "['a b'])\ndef test_quick(x):\n    pass\n\n\n@pytest.mark.parametrize('x', ['c d'])\ndef test_hangs(x):\n"
            "    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'], start_new_session=True)"
            "\n    Path(__file__).with_name('child').write_text(str(child.pid))\n    time.sleep(600)\n"),
            ["test_x.py::test_quick", "test_x.py::test_hangs"])
        late = pool.submit(stage, "late", (   # passes run 1; run 2 fails test_flaky and hangs in test_late (a session
            "import time\nfrom pathlib import Path\n\nimport pytest\n\nRUNS = Path(__file__).with_name('runs')\n\n\n"
            "@pytest.fixture(scope='module')\ndef browser():\n    return None\n\n\ndef test_flaky(browser):\n"   # a run)
            "    RUNS.write_text(str(n := int(RUNS.read_text() if RUNS.exists() else 0) + 1))\n"
            "    assert n == 1, f'run {n} of the flaky test fails'\n\n\ndef test_late(browser):\n"
            "    if RUNS.read_text() != '1':\n        time.sleep(600)\n"), ["test_x.py::test_flaky", "test_x.py::test_late"])
        listing = pool.submit(stage, "listing", (   # its import hangs the stage's collection
            "import subprocess, sys, time\nfrom pathlib import Path\n\nchild = subprocess.Popen([sys.executable, '-c', "
            "'import time; time.sleep(600)'])\nPath(__file__).with_name('child').write_text(str(child.pid))\n"
            "time.sleep(600)\n\n\ndef test_never():\n    pass\n"), ["test_x.py::test_never"])
        (flake, meta), (flaked, _), (listed, _) = hung.result(), late.result(), listing.result()
    assert (flake["passed"], flake["done"], len(flake["walls"])) == (False, 0, 1)
    assert [(f["test"], f.get("capped")) for f in flake["failures"]] == [("test_x.py::test_hangs[c d]", True)]
    assert 0 < flake["walls"][0] <= flake["wall_s"] and flake["wall_s"] >= fullsuite.FLAKE_CAP
    assert "test_x.py::test_hangs[c d] capped: no passing run within 15 s" in fullsuite.describe(
        {"key": "k", "subject": "s", "mode": "changed", "pytest_args": [], "state": "done", "exit_code": 0,
         "flake_tests": flake["tests"], "flake": flake}, meta)
    assert (flaked["passed"], flaked["done"], len(flaked["walls"]), flaked["note"]) == (
        False, 1, 2, "run 2 ended at the stage's 15 s")
    assert [(f["test"], f["run"], f.get("capped")) for f in flaked["failures"]] == [("test_x.py::test_flaky", 2, None)]
    assert "test_x.py::test_flaky FAILED" in "\n".join(flaked["failures"][0]["tail"])
    assert (listed["passed"], [f["test"] for f in listed["failures"]], listed["walls"]) == (
        False, ["(their collection: exit past 15 s)"], [])
    assert [name for name in ("hung", "late") if (tmp_path / name / "suite-k.flake.out").exists()] == []
    for name in ("hung", "listing"):
        child, deadline = int((tmp_path / name / "child").read_text()), time.time() + 10
        while _running(child) and time.time() < deadline:
            time.sleep(0.1)
        assert not _running(child), f"the ended {name}'s child outlived it"


def test_the_flake_stage_counts_a_grouped_cases_runs_under_the_id_its_collection_gives_it(tmp_path, monkeypatch):
    """Under ``--dist loadgroup`` a worker names a case of an xdist group
    (each frozen_app test, ``tests/conftest.py``) ``<id>@<group>``, where the
    stage's collection, with no workers, names it ``<id>``: its passing runs
    count under that id (a steady grouped case passes, never capped), and so
    does a failure's name; an ``@`` in a parameter stays."""
    _quick_flake(monkeypatch)
    monkeypatch.setattr(fullsuite, "FLAKE_WORKERS", 1)   # the suffix is a worker's
    monkeypatch.setattr(fullsuite, "FLAKE_RUNS", 1)
    (tmp_path / "conftest.py").write_text(   # tests/conftest.py's grouping
        "import pytest\nfrom _pytest.nodeid import NodeId\n\n\ndef pytest_collection_modifyitems(config, items):\n"
        "    for item in items:\n        item.add_marker(pytest.mark.xdist_group('frozen_app'))\n"
        "        if getattr(config.option, 'loadgroup', False):\n"
        "            item._id = NodeId.parse(f'{item.nodeid}@frozen_app')\n", encoding="utf-8")
    (tmp_path / "test_x.py").write_text("import pytest\n\n\n@pytest.mark.parametrize('x', ['a b'])\ndef test_app(x):\n"
                                        "    pass\n", encoding="utf-8")
    meta = tmp_path / "suite-k.meta"
    flake = fullsuite.flake_stage(meta, {"key": "k", "worktree": str(tmp_path), "cap_s": 600,
                                         "flake_tests": ["test_x.py::test_app"]})
    assert "PASSED test_x.py::test_app[a b]@frozen_app" in meta.with_suffix(".log").read_text(encoding="utf-8")
    assert (flake["passed"], flake["done"], flake["cases"], flake["failures"]) == (True, 1, 1, [])
    assert [fullsuite.case_id(said) for said in ("t.py::t@frozen_app", "t.py::t[a@b]", "t.py::t[a@b]@frozen_app",
                                                 "a@b/t.py::t", "t.py::t[x]@frozen_app]")] == [
        "t.py::t", "t.py::t[a@b]", "t.py::t[a@b]", "a@b/t.py::t", "t.py::t[x]"]   # the last: -rfE's


def test_a_flake_stages_test_that_starts_nothing_once_a_session_has_its_five_runs_in_one_session(tmp_path, monkeypatch):
    """Step 4.4dx12: a test that reaches no fixture of the suite's own
    wider than a test (a module's or the session's, as the browser, the
    wheel under Pyodide or the site are: set up once for five runs, they'd
    make the five one), the images' paths aside (``flake_repeat.PATHS``),
    has its FLAKE_RUNS runs in the first run's session, each a case of its
    own on one worker, one after another, where it took a session a run;
    one that reaches one, through a test-scoped fixture too, keeps a
    session a run, the later ones its own alone (pytest's tmp_path_factory
    is no fixture of the suite's). The block names the tests repeated; a
    repeat that fails is named with its own run, and the stage stops there."""
    _quick_flake(monkeypatch)
    monkeypatch.setattr(fullsuite, "FLAKE_WORKERS", 2)   # a case's runs on one worker (tests/conftest.py's groups)
    wide, runs = {"browser": "module", "pyodide": "session", "site": "module"}, fullsuite.FLAKE_RUNS
    paths = sorted(flake_repeat.PATHS)
    # Each worker of a session logs to a file of its own, stamped, its session xdist's run id: on Windows two
    # processes' appends to one file overwrite each other's lines (its C runtime seeks to the end, then writes: CI
    # lost 4 of 35), and a worker's parent is its venv launcher there, not the session's pytest.
    head = ("import time\nfrom pathlib import Path\n\nimport pytest\n\n\n"
            "def log(request):\n    run, worker = (request.config.workerinput[k] for k in ('testrunuid', 'workerid'))\n"
            "    with Path(__file__).with_name(f'log-{run}-{worker}').open('a') as f:\n"
            "        f.write(f'{time.time_ns()} {request.node.name} {run}-{worker} {run}\\n')\n\n\n")

    def stage(name: str, source: str, tests: list[str]) -> tuple[dict, Path]:
        (folder := tmp_path / name).mkdir()
        (folder / "conftest.py").write_text(   # tests/conftest.py's grouping
            "import pytest\nfrom _pytest.nodeid import NodeId\n\n\n@pytest.hookimpl(tryfirst=True)\n"
            "def pytest_collection_modifyitems(config, items):\n    if getattr(config.option, 'loadgroup', False):\n"
            "        for item in items:\n            if groups := sorted({str(m.args[0]) for m in "
            "item.iter_markers('xdist_group')}):\n"
            "                item._id = NodeId.parse(f\"{item.nodeid}@{'_'.join(groups)}\")\n", encoding="utf-8")
        (folder / "test_x.py").write_text(source, encoding="utf-8")
        return fullsuite.flake_stage(folder / "suite-k.meta", {"key": "k", "worktree": str(folder), "cap_s": 600,
                                                              "flake_tests": tests}), folder

    flake, folder = stage("steady", head + "".join(
        f"@pytest.fixture(scope='{scope}')\ndef {n}():\n    return None\n\n\n"
        f"def test_{n}({n}, request):\n    log(request)\n\n\n" for n, scope in wide.items())
        + "@pytest.fixture\ndef page(site):\n    return site\n\n\ndef test_page(page, request):\n    log(request)\n\n\n"
        + "".join(f"@pytest.fixture(scope='session')\ndef {n}():\n    return None\n\n\n" for n in paths)
        + "@pytest.mark.parametrize('x', ['a', 'b'])\ndef test_pure(x, request):\n    log(request)\n\n\n"
        f"def test_bare({', '.join(paths)}, tmp_path, request):\n    log(request)\n",
        [f"test_x.py::test_{n}" for n in (*wide, "page", "pure", "bare")])
    ran: dict[str, list[tuple[str, str]]] = {}   # each case's runs as they ran: (its worker, its session)
    for _, name, worker, session in sorted((line.split() for log in folder.glob("log-*")
                                            for line in log.read_text().splitlines()), key=lambda row: int(row[0])):
        ran.setdefault(fullsuite.split(f"t.py::{name}")[0].removeprefix("t.py::"), []).append((worker, session))
    assert {name: (len(r), len({pid for pid, _ in r}), len({s for _, s in r})) for name, r in ran.items()} == {
        **{f"test_{n}": (runs, runs, runs) for n in (*wide, "page")}, **dict.fromkeys(
            ("test_pure[a]", "test_pure[b]", "test_bare"), (runs, 1, 1))}
    assert {r[0][1] for name, r in ran.items()} == {ran["test_browser"][0][1]}   # the first run's session
    assert (flake["passed"], flake["done"], len(flake["walls"]), flake["cases"], flake["repeated"]) == (
        True, runs, runs, len(wide) + 4, ["test_x.py::test_bare", "test_x.py::test_pure"])
    assert "(2 of them all 5 in the first run's session)" in fullsuite.describe(
        {"key": "k", "subject": "s", "mode": "changed", "pytest_args": [], "state": "done", "exit_code": 0,
         "flake_tests": flake["tests"], "flake": flake}, folder / "suite-k.meta")
    flaky, folder = stage("flaky", "from pathlib import Path\n\nRUNS = Path(__file__).with_name('runs')\n\n\n"
                          "def test_flaky():\n    RUNS.write_text(str(n := int(RUNS.read_text() if RUNS.exists()"
                          " else 0) + 1))\n    assert n != 3, f'run {n} of the flaky test fails'\n",
                          ["test_x.py::test_flaky"])
    assert (flaky["passed"], flaky["done"], len(flaky["walls"]), (folder / "runs").read_text()) == (False, runs, 1, "5")
    assert [(f["test"], f["run"]) for f in flaky["failures"]] == [("test_x.py::test_flaky", 3)]
    assert [fullsuite.split(case) for case in ("t.py::t[a-flake-run-3]", "t.py::t[flake-run-12]", "t.py::t[a]")] == [
        ("t.py::t[a]", 3), ("t.py::t", 12), ("t.py::t[a]", None)]


def _running(pid: int) -> bool:
    """Whether the process ``pid`` runs (a zombie, ended and not yet reaped, doesn't)."""
    if os.name == "nt":
        return f" {pid} " in subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                                            text=True).stdout
    return subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()[:1] not in (
        "", "Z")


def test_the_perf_gate_keeps_misses_as_debt_and_fails_only_a_regression_against_the_last_release_or_a_memory_peak(
        tmp_path):
    """D981-D985 and D1170 on fake timings: an op's verdict says when its
    median is over 3 s (the capped profile's 9 s; ``over``, or ``regressed``
    over a listed ceiling), past 1 s with no progress (D980; not a list's
    debt), or a sample's page froze in a gap: each is a perf-debt row that
    fails nothing (a Save's with the free disk its run left), and so is an
    op the last release never measured that errs, with its error; a
    download, whose write the browser's own bar shows, shows progress when
    its page part is within 1 s; an image's first check is within 3 s only
    with a moving bar (D982). An op blocks only as a regression against the
    last release's run (fullsuite.release_reference: the newest tag's
    receipt with verdicts, a run of every op first, else the release's
    before; never main's newer runs): ``slower``, its median over its budget
    and over that run's by more than 25 % and 0.5 s (it runs R more times
    first and fails only if the median of all still is: one spike can't
    fail it), or an error on an op that run measured; a memory peak blocks
    too (perf.blocking). The receipt's debt rows go to the debt ledger; the
    list may lower and drop but never add or raise against main's; changes
    reach the ops of their area."""
    def s(seconds, bar=0, progress=True):
        return {"s": seconds, "bar": bar, "progress": progress}
    slow, moving = [s(3.2), s(3.4), s(3.1)], [s(6.8, bar=5)] * 3
    saved = lambda seconds, page: [{**s(seconds, progress=False), "page": page}] * 3   # noqa: E731
    assert [perf.judge(*case)["verdict"] for case in (
        (slow, 3.0), (slow, 9.0), (slow, 3.0, 4.0), ([s(4.7)] * 3, 3.0, 4.0), (moving, 3.0, None, False, True),
        (moving, 3.0, 29.3, False, True), ([s(6.8, bar=1)] * 3, 3.0, None, False, True),
        ([s(1.5, progress=False)] * 3, 3.0),
        ([s(1.5, progress=False)] * 3, 3.0, None, True), ([{**s(2.0), "error": "timed out"}], 3.0),
        (saved(1.3, 1.2), 3.0, None, False, False, True), (saved(1.3, 0.01), 3.0, None, False, False, True),
        (saved(3.3, 0.01), 3.0, None, False, False, True), (saved(1.3, 0.01), 3.0))] == [
        "over", "pass", "listed", "regressed", "bar", "bar", "over", "no progress", "pass", "error",
        "no progress", "pass", "over", "no progress"]
    froze = "the page froze 400 ms in the head start before A12"
    assert [(r["verdict"], r["debt"], r["ok"]) for r in (
        perf.judge(slow, 3.0), perf.judge([s(1.5, progress=False)] * 3, 3.0), perf.judge([s(2.0)] * 3, 3.0),
        perf.judge([{**s(2.0), "froze": froze}, s(2.1), s(2.2)], 3.0), perf.judge([{**s(2.0), "error": "x"}], 3.0),
        perf.judge([{**s(2.0), "error": "x"}], 3.0, reference=2.0),
        perf.judge([s(3.6)] * 3, 3.0, reference=2.0), perf.judge([s(2.6)] * 3, 3.0, reference=2.0),
        perf.judge([s(1.4)] * 3, 1.0, reference=1.0), perf.judge([s(4.0)] * 3, 3.0, reference=3.5))] == [
        ("over", True, True), ("no progress", True, True), ("pass", False, True), ("pass", True, True),
        ("error", True, True), ("error", False, False), ("over", True, False), ("pass", False, True),
        ("over", True, True), ("over", True, True)]
    assert perf.judge(saved(1.3, 0.01), 3.0, browser_bar=True)["page"] == [0.01] * 3
    empty, bars = {"ceilings": {}, "debts": set()}, [{**s(6.8, bar=5), "page": 0.01}] * 3
    assert {k: v["verdict"] for k, v in perf.verdicts(   # D1053: Firefox's whole Save passes on its bar, no other's
        [("S49", "firefox"), ("S49", "webkit")], {("firefox", "S49"): bars, ("webkit", "S49"): bars}, empty,
        browser_bars={"S49"}).items()} == {"S49/firefox": "bar", "S49/webkit": "over"}
    times = {"A12": [[5.0, 3.2, 2.6], [2.0, 2.1, 2.2]], "A13": [[4.0, 4.1, 4.2], [4.0, 4.0, 4.1]],
             "A15": [[4.0, 4.1, 4.2]], "A24": [[290.0]]}
    asked = []

    def drive(run, targets):
        asked.append((run, dict(targets)))
        return {"samples": {op: [s(t) for batch in times[op][:1 + (n > perf.R)] for t in batch]
                            for op, n in targets.items()}}
    lst = {"ceilings": {"A24/app": 300.0}, "debts": [], "memory": {}, "untimed": {}}
    receipts, repo, at = tmp_path / "receipts", tmp_path / "repo", {}
    receipts.mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    for name in ("v1.0.0", "v1.0.1", "main"):   # v1.0.1's run never got to its perf stage: v1.0.0's is the reference
        _git(repo, "commit", "-q", "--allow-empty", "-m", name)
        at[name] = _git(repo, "rev-parse", "HEAD")
        if name != "main":
            _git(repo, "tag", name)
    run = {"perf_args": ["--all"], "state": "done", "exit_code": 0, "perf": {"passed": True, "cases": {
        "A12/app": {"median": 2.0}, "A13/app": {"median": 3.0}}}}
    for name, m in (("release", run | {"head": at["v1.0.0"], "finished_at": "1"}),
                    ("lane", run | {"head": at["v1.0.0"], "finished_at": "2", "perf_args": ["--select"]}),
                    ("unrun", run | {"head": at["v1.0.1"], "finished_at": "3", "perf": {"passed": False}}),
                    ("main", run | {"head": at["main"], "finished_at": "4", "perf": {"passed": True, "cases": {
                        "A12/app": {"median": 9.0}}}})):
        (receipts / f"suite-{name}.meta").write_text(json.dumps(m), encoding="utf-8")
    reference = fullsuite.release_reference(receipts, repo)
    assert reference.name == "suite-release.meta"
    medians = {k: r["median"] for k, r in json.loads(reference.read_text())["perf"]["cases"].items()}
    got, _, _ = perf.measure([("A12", "app"), ("A13", "app"), ("A15", "app"), ("A24", "app")], drive, lst,
                             reference=medians)
    assert {k: (r["verdict"], r["ok"]) for k, r in got.items()} == {
        "A12/app": ("pass", True), "A13/app": ("over", False), "A15/app": ("over", True), "A24/app": ("listed", True)}
    assert asked == [("app", {"A12": 3, "A13": 3, "A15": 3, "A24": 3}), ("app", {"A12": 6, "A13": 6})]
    got |= {"A96/app": perf.judge([{**s(600.4), "error": "timed out"}], 3.0),   # new to the release
            "A95/app": perf.judge([{**s(0.0), "error": "stopped"}], 3.0, reference=1.1)}   # it measured it
    block = {"cases": got, "memory": {"capped-app": {"peak": 7 * 2**30, "ok": False}}, "native_failures": [], "list": []}
    assert [line.split(" (")[0] for line in perf.blocking(block)] == [
        "A13/app: slower than the release's 3.0 s", "A95/app: error", "memory capped-app: 7.00 GiB"]
    rows = perf.debt_rows(got, saves={"A13"}, free={"app": 52 * 2**30})
    assert [(row["op"], row["verdict"], row.get("free_disk_gib")) for row in rows] == [
        ("A13/app", "over", 52.0), ("A15/app", "over", None), ("A24/app", "listed", None), ("A96/app", "error", None)]
    assert perf.debt_line(rows[-1]) == "A96/app: error (timed out)"
    meta = receipts / "suite-k.meta"
    fullsuite.ledger(meta, {"key": "k", "head": "f" * 40, "perf": {"debt": rows}})
    assert [json.loads(line)["op"] for line in (receipts / fullsuite.DEBT_LEDGER).read_text().splitlines()] == [
        "A13/app", "A15/app", "A24/app", "A96/app"]
    main = {"ceilings": {"A15/app": 4.8, "S14/webkit": 21.0, "S03/lag": 29.3}, "debts": ["A15/app"], "memory": {},
            "untimed": {}}
    mine = {**main, "ceilings": {"A15/app": 5.0, "S14/webkit": 21.0, "A06/app": 9.0}, "debts": ["A15/app", "A06/app"]}
    assert perf.check_list(mine, main) == ["A06/app: added to the list (ceiling 9.0 s)",
                                           "A15/app: its ceiling raised, 4.8 -> 5.0 s", "A06/app: a new progress debt"]
    assert perf.check_list(mine, None) == []   # the first record
    results = {"A15/app": perf.judge([s(4.0)] * 3, 3.0, 4.8, True), "S14/webkit": perf.judge([s(2.0)] * 3, 3.0, 21.0),
               "A06/app": perf.judge([s(7.0, progress=False)] * 3, 3.0),
               "S03/lag": perf.judge(moving, 3.0, 29.3, False, True)}   # D982: a moving bar leaves the list
    assert perf.updated(main, results, {}, first=False) == {
        "ceilings": {"A15/app": 4.6}, "debts": [], "memory": {}, "untimed": {}}
    assert perf.updated(perf.listed(None), results, {}, first=True)["ceilings"] == {"A15/app": 4.6, "A06/app": 8.1}
    assert perf.listed(perf.render(main)) == main


def test_a_changed_path_times_only_the_perf_ops_of_the_groups_that_load_it_and_the_perf_tools_every_op():
    """``perf.select`` (``perf.REACH``): a path times the ops of the hosts
    and groups that load it, an unlisted path under ``src/`` or ``web/``
    every op, and so does the perf gate's own driver or judge (Step 4.46a:
    its change ran no perf stage, and land.py, which asks a perf block of
    what ``perf.select`` times, asked none), a test or a doc none; each
    narrow row's loaders are still its
    own (Step 4.43a: the app's stack dumps, the Tracker's modules and
    pictures, the site worker's Check parts), so an import that widens one
    fails here, not as a missed op."""
    pairs = lambda hosts, groups: {(host, group) for host in hosts for group in groups}   # noqa: E731
    both, every = ("app", "site"), pairs(("app", "site"), perf.GROUPS)
    assert perf.select(["src/azurkit/tools/randomizer/x.py", "scripts/web_tools.py"]) == (
        pairs(("app",), ("randomizer", "tracker")) | pairs(("site",), perf.GROUPS))
    assert perf.select(["src/azurkit/_stacks.py"]) == pairs(("app",), perf.GROUPS)
    for path in ("web/tracker.mjs", "web/mapview.mjs", "web/art.mjs", "web/art/1-x/w1.png", "web/art/icons.css"):
        assert perf.select([path]) == pairs(both, ("start", "image", "randomizer", "tracker")), path
    assert perf.select(["web/parts.mjs"]) == pairs(("site",), ("start", "characters"))
    for path in ("web/app.mjs", "web/worker.mjs", "web/characters.mjs", "web/variants.mjs", "src/azurkit/core/native.py",
                 "tests/_perf.py", "tests/_page.py", "scripts/perf.py"):
        assert perf.select([path]) == every, path
    assert perf.select(["AGENTS.md", "tests/test_x.py"]) == set()
    imports = re.compile(r'^import [^;]*? from "\.{1,2}/([\w./]+\.mjs)";', re.M)
    importers = {}
    for module in (ROOT / "web").rglob("*.mjs"):
        for name in imports.findall(module.read_text(encoding="utf-8")):
            importers.setdefault((module.parent / name).resolve().relative_to(ROOT).as_posix(), set()).add(
                module.relative_to(ROOT).as_posix())
    assert {name: importers.get(name) for name in ("web/tracker.mjs", "web/mapview.mjs", "web/art.mjs",
                                                   "web/parts.mjs")} == {
        "web/tracker.mjs": {"web/app.mjs"}, "web/mapview.mjs": {"web/tracker.mjs"}, "web/art.mjs": {"web/tracker.mjs"},
        "web/parts.mjs": {"web/worker.mjs"}}
    stacks = {path.relative_to(ROOT / "src" / "azurkit").as_posix() for path in (ROOT / "src").rglob("*.py")
              if re.search(r"^\s*from azurkit import [^\n]*\b_stacks\b", path.read_text(encoding="utf-8"), re.M)}
    assert stacks and all(rel == "__main__.py" or rel.startswith("app/") for rel in stacks), stacks


def test_the_perf_gate_fails_a_run_whose_engine_answers_without_the_native_library_its_worktree_ships():
    """The perf gate's native assert (Step 4.3 native reach): each run's
    engine reports (``sdk.catalog``'s ``native``) are the library the
    worktree ships for the host, loaded, with its bytes' sha256[:12]; a
    twin's run, another library's bytes, no report, a twin's answer beside
    the library or no count of them fails, and a page whose engine runs
    without its library stops its pass (``Driver.engine``); a page leaving
    keeps its report, with the calls by then (``Driver.leave``)."""
    from azurkit.core import native
    app = perf.shipped(Path(perf.ROOT), native.target())
    site = perf.shipped(Path(perf.ROOT), perf.SIDE_MODULE)
    assert app[1] and site[1] and perf.shipped(Path(perf.ROOT), None) == (None, None)
    ran = {"loaded": True, "library": app[0], "sha12": app[1], "kernels": ["reach"], "why": None,
           "calls": {"kernel": 9, "twin": 0}}
    twin = {"loaded": False, "library": None, "sha12": None, "kernels": [], "why": "AZURKIT_NATIVE=0"}
    assert perf.native_failures({"app": [ran], "webkit": [ran | {"library": site[0], "sha12": site[1]}]},
                                {"app": app, "webkit": site}) == []
    assert perf.native_failures({"app": [twin], "webkit": [ran], "lag": []}, {"app": app, "webkit": site, "lag": site}) == [
        f"native app: the engine ran no library (AZURKIT_NATIVE=0), not the shipped {app[0]} ({app[1]})",
        "native lag: its engine reported no compiled kernels",
        f"native webkit: the engine ran {app[0]} ({app[1]}), not the shipped {site[0]} ({site[1]})"]
    assert perf.native_failures({"app": [ran | {"calls": {"kernel": 9, "twin": 2}}], "lag": [{k: v for k, v in ran.items() if k != "calls"}]},
                                {"app": app, "lag": app}) == [
        "native app: its Python twin answered 2 of the engine's reach calls",
        "native lag: its Python twin answered an unknown count of the engine's reach calls"]

    class Stub(_perf.Page):
        def __init__(self, report):
            self.report = report
            self.page = self
            self.closed = False

        def js(self, fn, arg=None):
            return self.report if fn in (_perf.NATIVE, _perf.CALLS) else pytest.fail(fn)

        def close(self):
            self.closed = True
    d = _perf.Driver(_perf.RUNS["app"], {}, Path(perf.ROOT), Path(perf.ROOT), None)
    d.engine(Stub(ran))
    with pytest.raises(RuntimeError, match=r"^the engine runs without its native library \(AZURKIT_NATIVE=0\)$"):
        d.engine(Stub(twin))
    assert d.native == [ran, twin]
    d.leave(leaving := Stub(answered := ran | {"calls": {"kernel": 9, "twin": 1}}))
    assert leaving.closed and d.native == [ran, twin, answered]


def test_the_lag_model_makes_each_of_the_workers_file_reads_late_and_stops_on_one_it_doesnt_know():
    """Safari's read model (the perf gate's lag run) makes every read of the
    player's File in ``web/worker.mjs`` and ``web/hasher.mjs`` 200 ms late, the blocks' FileReaderSync
    reads, the image check's awaited ones and Replace files' stream alike; a read or stream it doesn't know
    stops the run, naming its line. Its ``sw.js`` lists the texts it serves
    late, as the worker's install keeps no other bytes (D1013)."""
    import hashlib

    from scripts import web_tools
    from tests import _perf

    text = (ROOT / "web" / "worker.mjs").read_text(encoding="utf-8")
    late = _perf.lagged(text)
    assert late.count(f"performance.now() + {_perf.LAG_MS}") == 1 and late.count(_perf._WAIT) == 5
    files = {"worker.mjs": {"sha256": "0" * 64, "size": 1}, "app.mjs": {"sha256": "1" * 64, "size": 2}}
    sw = (ROOT / "web" / web_tools.WORKER).read_text(encoding="utf-8").replace(
        web_tools.RELEASE_LINE, f"const RELEASE = {json.dumps({'csp': '', 'files': files, 'name': 'n'})};")
    line = next(line for line in _perf.relisted(sw, {"/worker.mjs": late}).splitlines() if line.startswith("const RELEASE"))
    assert json.loads(line.removeprefix("const RELEASE = ").removesuffix(";"))["files"] == files | {"worker.mjs": {
        "sha256": hashlib.sha256(late.encode()).hexdigest(), "size": len(late.encode())}}
    hasher = (ROOT / "web" / "hasher.mjs").read_text(encoding="utf-8")
    assert _perf.lagged(hasher, _perf.HASHER_LAG).count(_perf._WAIT) == 1
    for added in ("const more = await file.slice(0, 1).arrayBuffer();", "const more = file.stream().getReader();"):
        with pytest.raises(SystemExit, match=re.escape(repr(added))):
            _perf.lagged(text.replace("async function prime(", f"{added}\nasync function prime(", 1))


def test_the_perf_gates_memory_counts_only_the_webkit_launchd_started_for_its_own_browser(monkeypatch):
    """The capped-site peak: a WebKit process that started during the run
    counts when ``launchctl print pid/N`` holds this run's mark in its PATH,
    or can't say (no record, or launchctl failing: counted, never laxer);
    another seat's doesn't, and its pid reused by ours, which started later,
    is asked about again and counted."""
    mine, theirs = f"PATH => {_perf.MARK}:/usr/bin", "PATH => /usr/bin"
    said = {"11": mine, "12": theirs, "13": "", "15": theirs}

    def launchctl(argv, **kwargs):
        asked.append(argv[-1])
        if argv[-1] == "pid/14":
            raise subprocess.TimeoutExpired(argv, 10)
        return types.SimpleNamespace(stdout=said[argv[-1].removeprefix("pid/")])
    asked: list[str] = []
    monkeypatch.setattr(_perf.subprocess, "run", launchctl)
    monkeypatch.setattr(_perf, "_launched", {})
    xpc = "/x/playwright/webkit-1/Contents/com.apple.WebKit.WebContent.xpc/Contents/MacOS/WebContent"
    rows = [(10, os.getpid(), "/x/playwright/driver/node", "t0"), (20, 10, "/x/pw_run", "t0"),
            *((pid, 1, xpc, "t0") for pid in (9, 11, 12, 13, 14, 15)), (16, 1, "/Applications/Safari.xpc/s", "t0")]
    before = {(9, "t0")}
    assert _perf.browser_pids(rows, before) == [20, 11, 13, 14]
    assert _perf.browser_pids(rows, before) == [20, 11, 13, 14] and len(asked) == 5   # each process asked about once
    said["15"] = mine
    assert _perf.browser_pids([(15, 1, xpc, "t1")], {(15, "t0")}) == [15]   # a pid reused: asked again, and not "before"


class _Stub(_perf.Page):
    """A page on a stub clock: each action's done-states (``costs``: ``{action:
    {done: ms}}``) true some ms after it, any other at once; the freeze
    probe's ``[due, ms]`` ticks."""

    def __init__(self, costs, ticks=()):
        super().__init__(types.SimpleNamespace(set_input_files=lambda *a: None))
        self.t, self.costs, self.ticks, self.at, self.clicks = 0.0, costs, list(ticks), {}, {}

    def load(self, url):
        pass

    def close(self):
        pass

    def now(self):
        return self.t

    def do(self, action, arg=None):
        self.clicks[action] = self.t
        self.at |= {done: self.t + ms for done, ms in self.costs.get(action, {}).items()}
        return self.t

    def js(self, fn, arg=None):   # an engine with its compiled kernels (Driver.engine)
        return {"loaded": True} if fn == _perf.NATIVE else self.do(fn, arg)

    def wait(self, done, timeout=900, arg=None):
        self.t = max(self.t, self.at.get(done, self.t))
        return self.t, True

    def poll(self, dones, seconds=None):
        return self.t, [self.t >= self.at.get(done, self.t) for done in dones]

    def settled(self):
        return self.t

    def events(self):
        self.late += [tick for tick in self.ticks if sum(tick) <= self.t]   # fired by now
        self.ticks = [tick for tick in self.ticks if sum(tick) > self.t]
        return []


def test_the_perf_gate_keeps_a_starved_sample_as_taken_names_it_and_counts_a_child_gone_mid_op(tmp_path, monkeypatch):
    """A sample past 1 s whose wall passes 1.3x its tree's CPU seconds
    stands as it was taken, with its tag, and counts in its op's verdict
    (D1107: it was taken once more and the second take replaced it, Step
    4.46a); the case names it. A child gone mid-op keeps what it used, so it
    reads as no starved sample, and a pid reused is another process (ps
    stubbed)."""
    start, new = "Sun Nov  1 08:22:00 2026", "Sun Nov  1 09:00:00 2026"
    reads = iter(["1 0 10 0:10.00 {0} /a\n2 1 10 0:05.00 {0} /a\n3 0 10 9:00.00 {0} /other\n",
                  "1 0 10 0:10.50 {0} /a\n2 1 10 0:09.00 {0} /a\n",
                  "1 0 10 0:10.50 {0} /a\n2 1 0 0:00.00 {0} (a)\n",   # killed, not reaped yet: ps reads it as 0
                  "1 0 10 0:10.50 {0} /a\n",
                  "1 0 10 0:10.50 {0} /a\n2 1 10 0:01.00 {1} /a\n"])
    monkeypatch.setattr(_perf.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=next(reads).format(start, new)))
    memory = _perf.Memory(lambda rows: [1])
    assert [memory.take() for _ in range(5)] == [15.0, 19.5, 19.5, 19.5, 20.5]
    assert not _perf.starved(4.5, 19.5 - 15.0)   # the child's 4 s stay though it exited

    spends = iter([1.0, 1.9, 0.1, 10.0])
    meter = types.SimpleNamespace(used=0.0)
    meter.take = lambda: setattr(meter, "used", meter.used + next(spends)) or meter.used

    def timed(ms, target=9):
        p = _Stub({"go": {"done": ms}})
        d.targets["A12"] = target
        d.act(p, "A12", "go", "done")
    d = _perf.Driver(_perf.RUNS["app"], {}, tmp_path, tmp_path, None)
    d.memory = meter
    timed(2000)   # starved: recorded at once, as taken
    assert d.samples["A12"] == [{"s": 2.0, "bar": 0, "progress": False, "late_ms": 0, "cpu": 1.0, "starved": True}]
    timed(2000)
    timed(900)     # under 1 s: never named
    timed(40000)   # past 30 s: it runs once
    assert [(s["s"], s.get("starved")) for s in d.samples["A12"]] == [(2.0, True), (2.0, None), (0.9, None),
                                                                      (40.0, True)]
    assert not any("retook" in s for s in d.samples["A12"]) and "taken once more" not in "".join(d.log)
    plain = {"s": 1.2, "bar": 0, "progress": True}
    named = [{"s": 4.0, "bar": 0, "progress": True, "cpu": 1.0, "starved": True}, plain, plain]
    got = perf.judge(named, 3.0)
    assert got["starved"] == [4.0] and "starved" not in perf.judge([plain] * 3, 3.0)
    untagged = [{k: v for k, v in s.items() if k != "starved"} for s in named]
    assert {k: v for k, v in got.items() if k != "starved"} == perf.judge(untagged, 3.0)
    took = [{"s": 4.2, "bar": 0, "progress": True, "starved": True}, {"s": 2.8, "bar": 0, "progress": True},
            {"s": 4.0, "bar": 0, "progress": True, "starved": True}]
    assert (perf.judge(took, 3.0)["median"], perf.judge(took, 3.0)["verdict"]) == (4.0, "over")


def test_the_perf_gate_clicks_3_s_after_a_change_and_marks_a_sample_whose_page_froze_in_a_gap(tmp_path):
    """D1006 and D1014 over a stub clock: a Track or Build after a change
    (an op with ``head_start``) is clicked 3 s after it and timed from the
    click (at once once the change's own wait passed 3 s; never a Build
    again); a tick of the freeze probe due in a gap (the head start, a
    dialog's wait) over 250 ms late marks the next sample (``froze``: a perf-debt row, D1170), a head start's
    timed from the change, and one no sample takes is a log line, never an error; a late
    tick under that, due in an action's own wait or before the gap only
    logs. One click's done-states race, each its own first true poll (the
    click's op takes its head start's freeze); a state made once is cloned
    anew."""
    def driven(costs, ticks):
        p = _Stub(costs, ticks)
        d = _perf.Driver(_perf.RUNS["app"], dict.fromkeys(("A12", "A16", "S18", "S19", "S20"), 9), tmp_path,
                         tmp_path / "usa.iso", None)
        d.sleep = lambda seconds: setattr(p, "t", p.t + seconds * 1000)
        d.fresh(p)
        return p, d

    def run(op, pick, dialog, ticks):   # a pick (the change), a dialog's wait, then Build: (its click, its sample)
        p, d = driven({"pick": {"picked": pick}, "build": {"built": 2000}}, ticks)
        d.act(p, None, "pick", "picked", change=True)
        if dialog:
            d.idle(p, "the save dialog", dialog)
        d.act(p, op, "build", "built")
        d.over()
        if op is None:
            return "logged", d.log[-1]
        s = d.samples[op][0]
        return p.clicks["build"], s["s"], s.get("froze"), s.get("gap_ms"), s["late_ms"]
    froze = "the page froze 400 ms in "
    assert [run(*row) for row in (
        ("A12", 500, 0, []), ("A12", 4000, 0, []), ("A16", 500, 0, []),
        ("A12", 500, 0, [(1000, 400)]), ("A12", 500, 0, [(1000, 200)]), ("A12", 500, 0, [(300, 400)]),
        ("A12", 500, 0, [(3500, 400)]), ("A16", 500, 1.0, [(1000, 400)]), (None, 500, 1.0, [(1000, 400)]),
    )] == [
        (3000, 2.0, None, 0, 0), (4000, 2.0, None, None, 0), (500, 2.0, None, None, 0),
        (3000, 5.0, froze + "the head start before A12", 400, 0), (3000, 2.0, None, 200, 0), (3000, 2.0, None, 0, 0),
        (3000, 2.0, None, 0, 400), (1500, 2.0, froze + "the save dialog", 400, 0),
        ("logged", "app: " + froze + "the save dialog, after the pass's last sample"),
    ]
    p, d = driven({"seed": {"typed": 0}, "track": {"tracked": 5000, "world": 50, "art": 100}}, [(1000, 400)])
    d.act(p, None, "seed", "typed", change=True)
    d.race(p, "S18", "track", {"S19": "world", "S18": "tracked", "S20": "art"}, after={"S20": "S18"})
    assert p.clicks["track"] == 3000 and {op: (d.samples[op][0]["s"], d.samples[op][0].get("froze")) for op in (
        "S18", "S19", "S20")} == {"S18": (8.0, froze + "the head start before S18"), "S19": (0.05, None),
                                  "S20": (0.0, None)}
    made = []
    one, two = (d.state("home", lambda f: (made.append(f), (f / "a").write_text("x"))) for _ in range(2))
    (one / "a").write_text("y")
    assert len(made) == 1 and one != two and (two / "a").read_text() == "x"


def test_a_gap_whose_page_froze_says_how_much_cpu_the_browser_ran_in_it(tmp_path, monkeypatch):
    """A frozen gap's mark (``froze``) names the CPU the browser's processes (their
    whole tree) used across it, read from the run's sampler either side of it
    (one sample taken as it ends): a page late while its browser ran was busy,
    one late while it used none was kept from running. A gap that didn't
    freeze takes no sample; with no sample either side it says nothing."""
    start = "Sun Nov  1 08:22:00 2026"
    reads = iter(["1 0 10 0:00.00 {0} /app\n5 0 10 0:01.00 {0} /browser\n6 5 10 0:00.50 {0} /page\n",
                  "1 0 10 0:00.00 {0} /app\n5 0 10 0:01.01 {0} /browser\n6 5 10 0:00.50 {0} /page\n",
                  "1 0 10 0:00.00 {0} /app\n5 0 10 0:01.02 {0} /browser\n6 5 10 0:00.51 {0} /page\n"])
    monkeypatch.setattr(_perf.subprocess, "run",
                        lambda *a, **k: types.SimpleNamespace(stdout=next(reads).format(start)))
    memory = _perf.Memory(lambda rows: [1], lambda rows: [5])
    for _ in range(3):
        memory.take()
    at = [t for t, _ in memory._seen]
    assert [memory.ran(at[1], at[2]), memory.ran(at[0], at[2]), memory.ran(at[2] + 1, at[2] + 2)] == [
        pytest.approx(0.02), pytest.approx(0.03), None]

    def frozen(ticks, ran):
        p = _Stub({"pick": {"picked": 500}, "build": {"built": 2000}}, ticks)
        d = _perf.Driver(_perf.RUNS["app"], {"A12": 9}, tmp_path, tmp_path / "usa.iso", None)
        d.sleep = lambda seconds: setattr(p, "t", p.t + seconds * 1000)
        d.fresh(p)
        taken = []
        d.watch = types.SimpleNamespace(take=lambda: taken.append(p.t), ran=lambda t0, t1: ran)
        d.act(p, None, "pick", "picked", change=True)
        d.act(p, "A12", "build", "built")
        return d.samples["A12"][0].get("froze"), taken
    assert [frozen([(1000, 400)], 0.02), frozen([(1000, 400)], None), frozen([(1000, 200)], 0.02)] == [
        ("the page froze 400 ms in the head start before A12 (the browser ran 20 ms of CPU in its 2.5 s)", [3000]),
        ("the page froze 400 ms in the head start before A12", [3000]), (None, [])]


def test_the_sites_tracker_view_times_its_world_map_from_its_own_click_and_track_comes_after_the_head_start(
        tmp_path, monkeypatch):
    """S19 is the Tracker view's world map timed from the view's click (a
    tab's open: no head start of its own), so a slow first draw shows in it;
    Track (S18) is clicked 3 s after the typed seed, at once when the view's
    open took longer, and S20 counts from Track's done."""
    view, track = _perf.click("rando-view-tracker"), _perf.click("track-seed")
    costs = {view: {_perf.WORLD: 0}, track: {_perf.TRACKED: 5000, _perf.ART_DONE: 100}}
    pages = []

    def page(_):
        pages.append(_Stub(costs))
        return pages[-1]

    def tracked(world_ms):
        costs[view][_perf.WORLD], pages[:] = world_ms, []
        d = _perf.Driver(_perf.RUNS["webkit"], dict.fromkeys(("S18", "S19", "S20"), 9), tmp_path,
                         tmp_path / "usa.iso", None)
        d.sleep = lambda seconds: setattr(d.p, "t", d.p.t + seconds * 1000)
        _perf.site_track(d, types.SimpleNamespace(new_page=dict), "http://127.0.0.1:9800/")
        return round(pages[0].clicks[track]), {op: d.samples[op][0]["s"] for op in ("S18", "S19", "S20")}
    monkeypatch.setattr(_perf, "Page", page)
    monkeypatch.setattr(_perf, "opened", lambda ctx: _perf.Page(ctx.new_page()))
    assert [tracked(ms) for ms in (50, 30_000)] == [
        (3000, {"S18": 5.0, "S19": 0.05, "S20": 0.0}), (30_000, {"S18": 5.0, "S19": 30.0, "S20": 0.0})]


def _apart(call):
    """``call`` run on a loop of its own, in a thread of its own, as a Playwright's sync object runs its calls."""
    with ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, call).result()


def _playwright(name: str, driver: int, never: str):
    """A stand-in browser ``name``'s browser, context and page under the Playwright driver ``driver``: their impl
    objects' calls answer at once, all but the one ``never`` names, which never answers."""
    async def given(value):
        return value

    def call(what, value=None):
        return lambda *_, **__: asyncio.sleep(600) if what == never else given(value)
    connection = types.SimpleNamespace(_transport=types.SimpleNamespace(_proc=types.SimpleNamespace(pid=driver)))
    browser = types.SimpleNamespace(contexts=[], browser_type=types.SimpleNamespace(name=name), _sync=_apart,
                                    _impl_obj=types.SimpleNamespace(close=call("browser close"), _connection=connection))
    context = types.SimpleNamespace(pages=[], browser=browser, _sync=_apart)
    page = types.SimpleNamespace(main_frame=None, context=context, _sync=_apart, on=lambda *_: None,
                                 remove_listener=lambda *_: None, _impl_obj=types.SimpleNamespace(
                                     evaluate=call("evaluate", 0), goto=call("goto"), close=call("close"),
                                     page_errors=call("errors", []), console_messages=call("console", [])))
    context._impl_obj = types.SimpleNamespace(new_page=call("new page", page), cookies=call("cookies", []),
                                              _connection=connection)
    return browser, context, page


def test_a_perf_pass_whose_page_call_never_answers_ends_by_name_and_the_run_goes_on(tmp_path, monkeypatch):
    """Step 4.37s: the perf stage's driver left a WebKit page's evaluate unanswered 1 h 43 min, the suite lock held
    and seven gates behind it: WebKit had ended the page's process (its GPU process unresponsive three times in 30 s,
    ``reason=GPUProcessCrashedTooManyTimes``) and told Playwright nothing. Each call the driver makes to a page, a
    context or a browser is bounded (``_perf.bounded``), so a pass whose call never answers ends, its ops' error naming
    the call, WebKit's ending (at once, as its log names it) or that it went unanswered past its bound, this run's
    WebKit processes (none a page's) and whether its browser still answers, the whole failure in the run's log, and
    the run goes on. A row a call kind: a WebKit page's evaluate in S60's pass whose log names its page's ending; a
    page's evaluate past its bound (the storage's clean a site pass starts with); a context's new page past its bound;
    then a browser's close past its bound. Stand-in Playwright objects, process listings and log."""
    from scripts import ci_resources
    driver = os.getpid()   # the stand-ins' ids from it, so none is the worker's own
    ui, network = driver + 1, driver + 2
    said: list[str] = []
    monkeypatch.setattr(ci_resources, "table", lambda timeout=0: [(driver, 1, 100, "node", "", 1 << 20),
                                                                  (ui, driver, 90, "Playwright", "", 1 << 20)])
    monkeypatch.setattr(ci_resources, "webkit_said", lambda since, browsers: said if ui in browsers else [])
    webkit = "/x/.tools/playwright/webkit-2370/Playwright.app/Contents"
    monkeypatch.setattr(_perf.Memory, "rows", staticmethod(lambda rss=None, cpu=None: [
        (driver, os.getpid(), "node", "t0"), (ui, driver, f"{webkit}/MacOS/Playwright", "t0"),
        (network, 1, f"{webkit}/Frameworks/WebKit.framework/Versions/A/XPCServices/com.apple.WebKit.Networking.xpc/"
                     "Contents/MacOS/com.apple.WebKit.Networking.Development", "t1")]))
    monkeypatch.setattr(_perf, "ours", lambda pid, started: True)
    for name, value in (("LOG", True), ("LOOK", 0.5), ("HEAR", 0.5), ("PROBE", 0.5), ("STALL", 1)):
        monkeypatch.setattr(_page, name, value)
    ending = (f"00:15:28 Playwright: [pageProxyID=22, webPageID=23, PID=28607] WebPageProxy::processDidTerminate: "
              f"(pid 28607), reason=GPUProcessCrashedTooManyTimes")
    processes = f"its WebKit processes: Networking {network}; no page's (WebContent) process"
    url = "http://127.0.0.1:9/"
    # each: its browser, the call that never answers, the log's lines on its page's ending, the pass, and its ops'
    # error (a pattern): the call and its seconds, the ending, the processes, the browser's probe
    for browser, never, lines, scenario, error in (
            ("webkit", "evaluate", [ending], _perf.site_ahead_track,
             r"site-ahead-track stopped: Ended: no answer in [01] s: the wait for \(\) => globalThis\.azurkit\?\.ready; "
             rf"WebKit ended its page's process \(reason=GPUProcessCrashedTooManyTimes\); {re.escape(processes)}; "
             "its browser still answers"),
            ("chromium", "evaluate", [], lambda d, ctx, url: _perf.clean_storage(ctx, url),
             r"site-ahead-track stopped: AssertionError: no answer in 1 s: async \(\) => \{ const root = await "
             r"navigator\.storage\.getDirectory\(\); .+; its browser still answers"),
            ("webkit", "new page", [], _perf.site_ahead_track,
             rf"site-ahead-track stopped: AssertionError: no answer in 1 s: the context's new page; {re.escape(processes)}; "
             "its browser still answers")):
        said[:] = lines
        _, ctx, _ = _playwright(browser, driver, never)
        d = _perf.Driver(_perf.RUNS[browser], {"S60": 1}, tmp_path, tmp_path / "usa.iso", None)
        began = time.monotonic()
        d.attempt("site-ahead-track", 3, ("S60",), lambda: scenario(d, ctx, url))   # the run goes on
        took, got = time.monotonic() - began, d.samples["S60"][0]["error"]
        assert re.fullmatch(error, got) and took < 10, (browser, never, got, took)
        assert d.log[0].startswith(f"{browser} site-ahead-track pass 4: ") and d.log[0].endswith(
            (processes if browser == "webkit" else "") or f"under its driver: node {driver} (100 s), Playwright {ui} "
            "(90 s)") and (ending in d.log[0]) == bool(lines), (browser, never, d.log)
    browser, _, _ = _playwright("chromium", driver, "browser close")
    with pytest.raises(AssertionError) as failed:
        _perf.shut(browser)
    assert str(failed.value) == (f"no answer in 1 s: the browser's close\n"
                                 f"under its driver: node {driver} (100 s), Playwright {ui} (90 s)")


class _Seeds(_Stub):
    """The app's page over a stub clock as Build, Cancel and a pick make it:
    a build answers 3 s after its click, 0.5 s for a seed this engine
    process built (a kept plan), its first stage record 0.25 s after it; a
    Cancel ends the process; a model's pick, a change, forgets a build that
    has answered, so ``BUILT`` never comes again (the page's wait times out)."""

    def __init__(self):
        super().__init__({})
        self.seed, self.made, self.answers, self.staged, self.forgot, self.picks = "", set(), 0.0, 0.0, False, []

    def do(self, action, arg=None):
        if action == _perf.SEED_ASK:
            self.seed = "azurkit"
        elif typed := re.fullmatch(r".*getElementById\(\"rando-seed\"\); b\.value = \"(\w+)\".*", action, re.S):
            self.seed = typed[1]
        elif action in (_perf.build_js(), _perf.CANCEL_EARLY):
            self.answers = self.t + (500 if self.seed in self.made else 3000)
            self.staged, self.forgot = self.t + 250, False
            if action == _perf.CANCEL_EARLY:
                self.made, self.answers = set(), self.t   # the process killed, another spawned
            else:
                self.made.add(self.seed)
        elif action == _perf.model("keylord"):
            self.picks.append(self.t < self.answers)
            self.forgot = self.t >= self.answers
        return super().do(action, arg)

    js = do

    def wait(self, done, timeout=900, arg=None):
        if done == _perf.BUILT and self.forgot:
            raise TimeoutError(f"timed out after {timeout:.0f} s: {done[:100]}")
        at = {_perf.BUILT: self.answers, _perf.ANSWERED: self.answers, _perf.STAGED: self.staged}.get(done)
        self.t = max(self.t, at if at is not None else self.t)
        return self.t, True


def test_a_site_builds_sample_logs_its_steady_memory_beside_the_resident_peak(tmp_path):
    """D17: the gate's line stays the resident peak; a site build's sample
    also keeps the heap its engine reported plus its pieces' bytes (what a
    busy browser's caches don't inflate), beside the peak so far."""
    class Page(_Stub):
        def js(self, fn, arg=None):
            return 3 << 30 if fn == _perf.STEADY else super().js(fn, arg)
    d = _perf.Driver(_perf.RUNS["webkit"], {"S14": 1}, tmp_path, tmp_path, None)
    d.memory = types.SimpleNamespace(peak=5 << 30, used=4.0, take=lambda: 4.0)
    d.act(Page({}), "S14", _perf.build_js(), _perf.BUILT)
    assert (d.samples["S14"][0]["steady"], d.samples["S14"][0]["resident"]) == (3 << 30, 5 << 30)
    assert d.log[-1].endswith("steady 3.00 GiB peak 5.00 GiB")


def test_each_later_visit_on_the_site_opens_in_its_browser_opened_again_on_the_profile(tmp_path, monkeypatch):
    """Step 4.4m: S02's return visit and S64's build at a later visit open in the browser closed and opened again on
    the pass's profile, never beside the first visit's closed page: WebKit keeps that page's process, every page it
    held resident (a keylord build's 4.12 GiB), for the site's service worker while a page of the site is open, so
    the capped peak summed both visits (7.17 GiB, of which the closed page's footprint was 1.03 GiB)."""
    class Page(_Stub):
        def js(self, fn, arg=None):
            return True if fn == "() => crossOriginIsolated" else super().js(fn, arg)
    page = Page({})
    monkeypatch.setattr(_perf, "Page", lambda _: page)
    monkeypatch.setattr(_perf, "opened", lambda ctx: _perf.Page(ctx.new_page()))
    monkeypatch.setattr(_perf, "_download", lambda d, p, op: None)
    browsers = []   # each browser's pages, as they open

    def browser(old=None):
        browsers.append(pages := [])
        return types.SimpleNamespace(new_page=lambda: pages.append(len(browsers)))
    d = _perf.Driver(_perf.RUNS["webkit"], {"S02": 2}, tmp_path, tmp_path / "usa.iso", None)
    d.reopened = browser
    _perf.site_start(d, browser(), "http://127.0.0.1:9800/")
    assert (browsers, [s.get("error") for s in d.samples["S02"]]) == ([[1], [2], [3]], [None, None])


def test_the_engine_ready_again_after_a_seeds_build_is_timed_from_the_builds_answer(tmp_path, monkeypatch):
    """R24 (R14's twin): the next op's wait after a big build, the worker
    replaced, counts from the build's answer, not its click."""
    page = _Stub({_perf.build_js(): {_perf.BUILT: 5000, _perf.RESTED: 6200}})
    monkeypatch.setattr(_perf, "Page", lambda _: page)
    monkeypatch.setattr(_perf, "opened", lambda ctx: _perf.Page(ctx.new_page()))
    d = _perf.Driver(_perf.RUNS["webkit"], {"S24": 1, "R24": 1}, tmp_path, tmp_path / "usa.iso", None)
    d.sleep = lambda seconds: setattr(page, "t", page.t + seconds * 1000)
    _perf.site_seed(d, types.SimpleNamespace(new_page=dict), "http://127.0.0.1:9800/")
    assert (d.samples["S24"][0]["s"], d.samples["R24"][0]["s"]) == (5.0, 1.2)


def test_the_app_seed_pass_picks_its_model_while_a_build_runs_and_waits_for_that_builds_own_answer(tmp_path):
    """Step 4.3 train B3 (the gate's A27-A30 errors, 1,800 s each): A30's
    pick is a small ask made while a build runs, so its build is of a seed
    no build has made (one of a kept plan answers within the second A30
    used to wait), the pick comes at the build's first stage record, and
    the pass waits for that build's own answer, never ``azurkit.build``,
    which a pick after the answer forgets: the pass ends with every op
    sampled."""
    page = _Seeds()
    d = _perf.Driver(_perf.RUNS["app"], dict.fromkeys(("A27", "A28", "A29", "A30"), 1), tmp_path,
                     tmp_path / "usa.iso", None)
    d.sleep = lambda seconds: setattr(page, "t", page.t + seconds * 1000)
    app = types.SimpleNamespace(launch=lambda d, ctx, op: (d.fresh(page), page)[1], quit=lambda p=None: None)
    _perf.app_seed(d, app, None)
    d.over()
    assert (page.picks, {op: len(d.samples[op]) for op in ("A27", "A28", "A29", "A30")},
            [s.get("error") for op in ("A27", "A28", "A29", "A30") for s in d.samples[op]]) == (
        [True], dict.fromkeys(("A27", "A28", "A29", "A30"), 1), [None] * 4)


def test_update_ceilings_on_a_narrow_run_keeps_the_untimed_ops_it_doesnt_reach(tmp_path, monkeypatch):
    """``perf.py --update-ceilings`` on a run that reaches no untimed op
    (a lane lowering its own rows) keeps the list's untimed ops the registry
    still can't time, and drops only one the registry now times."""
    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(_perf.OPS, "S15", dataclasses.replace(_perf.OPS["S15"], untimed="out of memory"))
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    on_main = {"ceilings": {"A15/app": 6.1}, "debts": [], "memory": {}, "untimed": {"S15": "out of memory", "S14": "x"}}
    (repo / perf.CEILINGS).write_text(perf.render(on_main), encoding="utf-8")
    _git(repo, "add", perf.CEILINGS)
    _git(repo, "commit", "-q", "-m", "main")
    assert perf.main([str(repo), "--select", "app:tracker", "--ops", "NOOP", "--update-ceilings",
                      "--json", str(tmp_path / "perf.json")]) == 0
    assert perf.listed((repo / perf.CEILINGS).read_text(encoding="utf-8")) == {**on_main,
                                                                              "untimed": {"S15": "out of memory"}}


def test_the_perf_gates_app_is_the_worktrees_wheel_in_a_venv_reading_the_database_it_ships(tmp_path):
    """The perf gate's app profile runs the app as a player installs it
    (``_perf.venv``): the worktree's wheel in a scratch venv, whose app reads
    the randomizer database the wheel ships instead of checking it again as a
    checkout does (round 1's A06: 7.8 s from a worktree, 3.5 s frozen), and
    finds the worktree's page where the installed app looks for it."""
    from tests import _perf

    python = _perf.venv(ROOT, tmp_path / "app")
    code = ("import sys; from azurkit import app; from azurkit.tools.randomizer import dbcache; "
            "from azurkit.tools.randomizer.planner.loader import DATA_DIR; "
            "print(app.PAGE, dbcache.shipped(DATA_DIR) is not None, sys.prefix, sep='\\n')")
    page, shipped, prefix = subprocess.run([python, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True,
                                           check=True, timeout=300).stdout.splitlines()
    assert (shipped, Path(prefix).resolve()) == ("True", (tmp_path / "app" / "venv").resolve())
    assert sorted(f.relative_to(page) for f in Path(page).rglob("*")) == sorted(
        f.relative_to(ROOT / "web") for f in (ROOT / "web").rglob("*"))

def _git(cwd, *args):
    return subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t",
                           "-c", "commit.gpgsign=false", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _repo(tmp_path, monkeypatch):
    """A repository whose main has one commit, a lane worktree on ``p2/x``
    and an empty receipts folder: ``(repo, lane, receipts, main's commit)``."""
    repo, lane, receipts = tmp_path / "repo", tmp_path / "lanes" / "x", tmp_path / "receipts"
    monkeypatch.setenv("AZURKIT_RECEIPTS", str(receipts))
    receipts.mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _git(repo, "commit", "-q", "--allow-empty", "-m", "a")
    _git(repo, "worktree", "add", "-q", "-b", "p2/x", str(lane), "main")
    return repo, lane, receipts, _git(repo, "rev-parse", "HEAD")


def _receipt(receipts, head, **fields):
    m = {"key": f"{head[:12]}-0", "head": head, "clean": True, "state": "done", "exit_code": 0, "mode": "full",
         "base": None, "finished_at": "2026-10-28T00:00:00", "vanilla_run": 2, "europe_run": 1} | fields
    (receipts / f"suite-{m['key']}.meta").write_text(json.dumps(m), encoding="utf-8")


def test_a_gitignored_file_under_the_tree_leaves_the_receipt_unclean_and_moves_its_key(tmp_path, monkeypatch):
    """Step 4.46a: a gitignored file on disk under the tree (a fixture
    ``*.xbr`` whose folder ``git add`` staged nothing of) is one the run may
    read and HEAD lacks: its receipt isn't clean, so land.py refuses it, its
    key moves with the file and the receipt names it. What tools write
    there (``__pycache__``, a ``.pyc``) leaves it clean."""
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    (lane / ".gitignore").write_text("*.xbr\n__pycache__/\n*.py[cod]\n", encoding="utf-8")
    _git(lane, "add", ".gitignore")
    _git(lane, "commit", "-q", "-m", "ignore")
    (lane / "tests" / "__pycache__").mkdir(parents=True)
    (lane / "tests" / "__pycache__" / "a.cpython-314.pyc").write_bytes(b"x")
    clean = fullsuite.prepare(lane, False, "main")
    assert clean["clean"] and "ignored" not in clean
    (lane / "tests" / "x.xbr").write_bytes(b"fixture")
    _git(lane, "add", "tests")   # stages nothing: the file is ignored
    held = fullsuite.prepare(lane, False, "main")
    assert (held["clean"], held["ignored"]) == (False, ["tests/x.xbr"]) and held["key"] != clean["key"]
    (lane / "tests" / "x.xbr").write_bytes(b"another")
    assert fullsuite.prepare(lane, False, "main")["key"] != held["key"]


def test_land_fast_forwards_main_only_with_a_passing_receipt_and_removes_the_lane(tmp_path, monkeypatch):
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    _git(lane, "commit", "-q", "--allow-empty", "-m", "b")
    top = _git(lane, "rev-parse", "HEAD")
    _git(repo, "branch", "p2/y", base)
    for refused in ({"exit_code": 1}, {"vanilla_run": 0}, {"europe_run": None},   # D26: both tiers ran
                    {"mode": "changed", "base": base, "flake_tests": ["t"], "flake": {"passed": False}}):
        _receipt(receipts, top, **refused)
        assert land.land(repo, "p2/x")[0] == 1, refused
    _receipt(receipts, top[:11] + "f", clean=False)
    assert land.land(repo, "p2/x")[0] == 1
    _receipt(receipts, top, mode="changed", base=base, flake_tests=["t"], flake={"passed": True})
    assert land.land(repo, "p2/x") == (0, f"land: moved main {base[:12]} -> {top[:12]} (p2/x; receipt "
                                          f"{top[:12]}-0, changed)")
    assert _git(repo, "rev-parse", "main") == top and not lane.exists()
    assert _git(repo, "branch", "--list", "p2/x") == ""
    _git(repo, "switch", "-q", "p2/y")
    _git(repo, "commit", "-q", "--allow-empty", "-m", "c")
    _receipt(receipts, _git(repo, "rev-parse", "HEAD"))
    code, why = land.land(repo, "p2/y")
    assert code == 1 and "doesn't fast-forward from main" in why


def test_land_needs_a_perf_block_blocking_nothing_for_src_or_web_and_a_list_that_only_shrinks(tmp_path, monkeypatch):
    """D981 and D1170: a stack changing src/ or web/ lands only on a receipt
    with a perf block (one whose stage ran) in which nothing blocks, read from
    its verdicts: a debt row doesn't, an op the last release never measured
    that errs among them (an older perf.py failed the block on it), while an
    error on an op the release measured, an error row with no reference (an
    older perf.py's), an op slower than there or a memory peak does; any
    stack, one changing only tests/perf_ceilings.toml too, is refused when its
    list adds an op or raises a ceiling against main's. No landing waits for a
    release (a release tags a commit on main)."""
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    (lane / "src").mkdir()
    (lane / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (lane / "tests").mkdir()
    (lane / perf.CEILINGS).write_text(perf.render({"ceilings": {"A15/app": 4.8}, "debts": [], "memory": {},
                                                   "untimed": {}}), encoding="utf-8")
    _git(lane, "add", "src/a.py", perf.CEILINGS)
    _git(lane, "commit", "-q", "-m", "src")
    top = _git(lane, "rev-parse", "HEAD")
    _receipt(receipts, top)
    code, why = land.land(repo, "p2/x")
    assert code == 1 and "and a perf block blocking nothing" in why
    old = {"verdict": "error", "ok": False, "slower": False, "debt": False, "error": "timed out after 600 s"}
    erring = old | {"reference": None, "debt": True}
    new = {"passed": False, "cases": {"A96/app": erring}, "memory": {}, "native_failures": [], "list": [],
           "failures": ["A96/app: error (timed out after 600 s)"]}
    for block in ({"passed": False}, new | {"cases": {"A96/app": old}},
                  new | {"cases": {"A96/app": erring | {"reference": 0.4}}},
                  new | {"cases": {"A13/app": {"verdict": "over", "slower": True, "reference": 3.0, "median": 4.1,
                                               "budget": 3.0}}},
                  new | {"memory": {"capped-app": {"peak": 7 * 2**30, "ok": False}}}):
        _receipt(receipts, top, perf_args=["--select", "app:build"], perf=block)
        assert land.land(repo, "p2/x", dry_run=True)[0] == 1, block
    _receipt(receipts, top, perf_args=["--select", "app:build"], perf=new)
    assert land.land(repo, "p2/x")[0] == 0   # main had no list: the first record
    _git(repo, "switch", "-q", "-c", "p2/y")
    for ceilings, landed in (({"A15/app": 60.0}, False), ({"A15/app": 4.8, "A01/app": 9.0}, False),
                             ({"A15/app": 4.0}, True)):
        (repo / perf.CEILINGS).write_text(perf.render({"ceilings": ceilings, "debts": [], "memory": {},
                                                       "untimed": {}}), encoding="utf-8")
        _git(repo, "commit", "-q", "-m", "the list alone", perf.CEILINGS)
        _receipt(receipts, _git(repo, "rev-parse", "HEAD"), mode="changed", base=_git(repo, "rev-parse", "main"))
        code, why = land.land(repo, "p2/y", dry_run=True)
        assert (code == 0) == landed and (landed or "grows main's list" in why), why
        if not landed:
            _git(repo, "reset", "-q", "--hard", "main")


def test_a_batchs_last_receipt_runs_the_perf_stage_its_entries_deferred_and_its_block_covers_each_landing(
        tmp_path, monkeypatch):
    """D1215's P1: ``--perf-later`` runs pytest and the flake stage and
    leaves the perf stage ``deferred`` (status 0; a key that names no
    selection, so main moving keeps it); ``--perf-later --perf-now`` runs
    it alone, its selection made against main's head then (``perf_base``),
    the receipt's pytest fields kept (one that never ran leaves it deferred
    to run again). land.py lands a deferred stack the perf stage times
    (``src/``, or ``scripts/web_tools.py`` outside ``src/`` and ``web/``)
    only on a later receipt's perf block that covers it: its head holds the
    stack's, its perf ran against main or a commit main holds, timed every
    op the stack's changes reach and blocks nothing."""
    repo, lane, receipts, base = _repo(tmp_path, monkeypatch)
    (lane / "src").mkdir()
    (lane / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(lane, "add", "src/a.py")
    _git(lane, "commit", "-q", "-m", "a")
    a = _git(lane, "rev-parse", "HEAD")
    later = fullsuite.prepare(lane, True, a, perf_later=True)
    _git(repo, "update-ref", "refs/heads/main", a)   # main moves (a batch ahead landed): the key holds
    assert fullsuite.prepare(lane, True, a, perf_later=True)["key"] == later["key"] != fullsuite.prepare(
        lane, True, a)["key"]
    assert (later["perf_base"], later["perf_args"][0], later["args"][-1]) == (base, "--select", "--perf-later")
    _git(repo, "update-ref", "refs/heads/main", base)
    m = fullsuite.stages(receipts / "suite-a.meta", later | {"exit_code": 0, "state": "running"}) | {"state": "done"}
    assert m["perf"] == {"deferred": True} and fullsuite.status_code(m) == 0 and fullsuite.waits(m)
    assert "deferred to its batch's perf stage" in fullsuite.describe(m, receipts / "suite-a.meta")
    meta = receipts / "suite-a.meta"
    fullsuite.save(meta, m | {"state": "queued", "perf_now": True, "runner_pid": os.getpid(), "flakes": [{"test": "t"}]})
    monkeypatch.setitem(sys.modules, "fcntl", types.SimpleNamespace(LOCK_EX=2, LOCK_NB=4, LOCK_UN=8,
                                                                    flock=lambda fd, op: None))
    timed, unrun = [], {"passed": False, "failures": ["the load stayed at 50.0"]}
    for block in (unrun, {"passed": True, "cases": {}, "debt": []}):
        monkeypatch.setattr(fullsuite, "perf_stage", lambda meta, m, block=block: timed.append(m["perf_args"]) or {
            "pairs": m["perf_args"][1].split(","), **block})
        assert fullsuite.runner(meta) == 0
        m = fullsuite.load(meta)
        if block is unrun:   # a stage that never ran leaves the receipt deferred, to run again
            assert fullsuite.waits(m) and m["perf"]["note"].endswith("didn't run: the load stayed at 50.0")
            fullsuite.save(meta, m | {"state": "queued", "perf_now": True, "runner_pid": os.getpid()})
    assert (timed, m["perf_base"], m["state"], m["flakes"], fullsuite.deferred(m)) == (
        [later["perf_args"]] * 2, base, "done", [{"test": "t"}], False)
    every = sorted(f"{h}:{g}" for h, g in perf.select(["src/a.py"]))
    _git(lane, "switch", "-q", "-c", "p2/y")
    _git(lane, "commit", "-q", "--allow-empty", "-m", "b")
    b = _git(lane, "rev-parse", "HEAD")
    _git(lane, "switch", "-q", "p2/x")
    _receipt(receipts, a, mode="changed", base=base, perf_args=["--select", ",".join(every)], perf={"deferred": True})
    batch = {"mode": "changed", "base": a, "perf_args": ["--select", ",".join(every)]}
    ok = {"passed": True, "cases": {}, "memory": {}, "native_failures": [], "list": [], "pairs": every}
    code, why = land.land(repo, "p2/x", dry_run=True)
    assert code == 1 and "a later receipt of its batch covering it" in why, why
    for refused in ({"perf_base": base, "perf": ok | {"list": ["S01/webkit: added to the list"]}},   # it blocks
                    {"perf_base": a, "perf": ok},                       # its perf ran against a commit main lacks
                    {"perf_base": base, "perf": ok | {"pairs": every[1:]}},   # it timed less than a reaches
                    {"perf_base": base, "perf": {"deferred": True}}):   # deferred too
        _receipt(receipts, b, **batch | refused)
        assert land.land(repo, "p2/x", dry_run=True)[0] == 1, refused
    _receipt(receipts, b, **batch | {"perf_base": base, "perf": ok})
    assert land.land(repo, "p2/x") == (0, f"land: moved main {base[:12]} -> {a[:12]} (p2/x; receipt {a[:12]}-0, "
                                          f"changed; its perf deferred, covered by receipt {b[:12]}-0's)")
    assert land.land(repo, "p2/y")[0] == 0 and _git(repo, "rev-parse", "main") == b   # b on its own block
    tools = tmp_path / "lanes" / "w"   # perf.REACH times scripts/web_tools.py, outside src/ and web/
    _git(repo, "worktree", "add", "-q", "-b", "p2/w", str(tools), "main")
    (tools / "scripts").mkdir()
    (tools / "scripts" / "web_tools.py").write_text("x = 1\n", encoding="utf-8")
    _git(tools, "add", "scripts/web_tools.py")
    _git(tools, "commit", "-q", "-m", "w")
    _receipt(receipts, _git(tools, "rev-parse", "HEAD"), mode="changed", base=b, perf={"deferred": True},
             perf_args=["--select", ",".join(sorted(f"{h}:{g}" for h, g in perf.select(["scripts/web_tools.py"])))])
    code, why = land.land(repo, "p2/w", dry_run=True)
    assert code == 1 and "a later receipt of its batch covering it" in why, why


def test_lanes_devlog_bullets_merge_once_each_and_land_refuses_the_stale_copy_of_one_a_lane_edited(tmp_path):
    """Step 4.4dx1: with the repository's ``.gitattributes`` (git's union
    driver on ``docs/DEVLOG.md``), two lanes' bullets at the 1.0.0 section's
    end rebase onto each other with no conflict, each once. A lane whose
    later commit edits its own bullet rebases cleanly too, but union keeps
    the old line beside the new: ``devlog.stale`` names it (by its bold
    title, or most of its words alike) and land.py refuses the stack."""
    repo, log = tmp_path / "repo", Path(devlog.LOG)
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    (repo / "docs").mkdir()
    for rel in (Path(".gitattributes"), log):
        (repo / rel).write_bytes((ROOT / rel).read_bytes())
    _git(repo, "add", ".gitattributes", devlog.LOG)
    _git(repo, "commit", "-q", "-m", "main")

    def add(branch, *bullets):
        _git(repo, "switch", "-q", branch)
        for old, new in zip(("", *bullets), bullets):
            text = (repo / log).read_text(encoding="utf-8")
            (repo / log).write_text(text.replace(old + "\n", new + "\n") if old else text + new + "\n", encoding="utf-8")
            _git(repo, "commit", "-q", "-am", new)

    a, b, c, d = (f"- **Bullet {x}** (Step 9.{x}): what lane {x} did and how it was checked." for x in "abcd")
    c2 = c.replace("checked.", "checked, as its review asked.")
    _git(repo, "branch", "p2/b")
    add("main", a)
    add("p2/b", b)
    _git(repo, "rebase", "-q", "main", "p2/b")   # the landing queue's rebase
    text = (repo / log).read_text(encoding="utf-8")
    assert text.endswith(f"{a}\n{b}\n") and text.count(a) == text.count(b) == 1 and devlog.stale(text) == []
    _git(repo, "switch", "-q", "-C", "main")   # b lands
    _git(repo, "branch", "p2/c")
    add("p2/c", c, c2)   # the lane's later commit edits its own bullet
    add("main", d)
    _git(repo, "rebase", "-q", "main", "p2/c")
    text = (repo / log).read_text(encoding="utf-8")
    at = text.splitlines().index(c) + 1
    assert text.endswith(f"{d}\n{c}\n{c2}\n")   # union kept the old line
    assert devlog.stale(text) == [f"{devlog.LOG}: lines {at} and {at + 1} are both **Bullet c**: keep one (a union "
                                  f"merge keeps a lane's edited bullet beside its old line)"]
    code, why = land.land(repo, "p2/c", dry_run=True)
    assert code == 1 and why.startswith("land: p2/c's developer log holds a bullet twice") and "**Bullet c**" in why
    edits = "\n".join(["## [1.0.0]", c.replace("**Bullet c**", "Bullet c"), c2.replace("**Bullet c**", "C"), a,
                       "## [0.9.0]", a, a])   # an edit that drops the title; a in two releases, and twice in one
    assert [why.split(" (")[0] for why in devlog.stale(edits)] == [
        f"{devlog.LOG}: lines 2 and 3 are one bullet twice", f"{devlog.LOG}: lines 6 and 7 are both **Bullet a**: keep one"]


def test_the_landing_tools_read_gits_output_as_utf8_whatever_the_locales_code_page(tmp_path, monkeypatch):
    """Step 4.4dx1: Windows' CPython 3.14 decodes a text subprocess's output
    in the locale's code page (cp1252 on CI's runners), which has no byte
    0x8F of the developer log's ``●``: ``fullsuite.git``, which land.py reads
    the log with, decodes git's output as UTF-8 on any runner."""
    _git(tmp_path, "init", "-q", "-b", "main", str(repo := tmp_path / "repo"))
    (repo / "log.md").write_text("- ● done\n", encoding="utf-8")
    _git(repo, "add", "log.md")
    _git(repo, "commit", "-q", "-m", "log")
    run = subprocess.run

    def windows(*args, text=False, encoding=None, **kw):   # a text read with no encoding named gets the code page
        return run(*args, text=text, encoding=encoding or ("cp1252" if text else None), **kw)

    monkeypatch.setattr(subprocess, "run", windows)
    assert fullsuite.git(repo, "show", "HEAD:log.md") == "- ● done\n"


def test_the_perf_gate_logs_firefoxs_tree_peak_and_no_verdict_or_list_reads_it(tmp_path, monkeypatch):
    """Firefox's Save holds gigabytes in its parent, so its first record keeps
    the tree's peak (``tree_peaks``, the run's kept file too), even over 6 GiB;
    only the capped profile's peak is judged or listed, so this one fails
    nothing and adds nothing to the list."""
    from azurkit.core import gate
    from scripts import web_tools

    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    on_main = {"ceilings": {}, "debts": [], "memory": {}, "untimed": {}}
    (repo / perf.CEILINGS).write_text(perf.render(on_main), encoding="utf-8")
    _git(repo, "add", perf.CEILINGS)
    _git(repo, "commit", "-q", "-m", "main")
    peak = 7 * 2**30
    image = types.SimpleNamespace(stat=lambda: types.SimpleNamespace(st_size=gate.USA.iso_size))
    monkeypatch.setattr(gate, "find", lambda release: image)
    monkeypatch.setattr(web_tools, "wheel", lambda *a, **k: tmp_path / "wheel")
    monkeypatch.setattr(web_tools, "site", lambda *a, **k: tmp_path / "site")
    monkeypatch.setattr(perf, "native_failures", lambda *_: [])
    monkeypatch.setattr(_perf, "drive", lambda wt, spec, todo, *_: {
        "samples": {op: [{"s": 0.5, "bar": 0, "progress": False}] * n for op, n in todo.items()}, "native": [],
        "memory_peak": peak if spec.memory else None, "memory_shared": False, "log": []})
    assert perf.main([str(repo), "--select", "site:build", "--ops", "S05", "--profiles", "site", "--browsers", "firefox",
                      "--update-ceilings", "--keep", str(tmp_path / "keep"), "--json", str(tmp_path / "perf.json")]) == 0
    block = json.loads((tmp_path / "perf.json").read_text(encoding="utf-8"))
    assert (block["tree_peaks"], block["memory"], block["passed"]) == ({"firefox": peak}, {}, True)
    assert json.loads((tmp_path / "keep" / "firefox.json").read_text(encoding="utf-8"))["memory_peak"] == peak
    assert perf.listed((repo / perf.CEILINGS).read_text(encoding="utf-8")) == on_main


def test_the_perf_gates_rerun_of_a_slower_op_adds_its_samples_to_the_first_and_judges_them_all(tmp_path, monkeypatch):
    """D1170's rerun, as the gate runs perf.py (no ``--keep``): an op slower
    than the release's takes R more samples (one past 30 s), each run asked
    only for those, and its verdict reads every sample, the first ones too
    (a changed area's first pass takes one each, D1215: A21's R from there)."""
    from azurkit.core import gate
    from scripts import web_tools

    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    (repo / perf.CEILINGS).write_text(perf.render(perf.listed(None)), encoding="utf-8")
    _git(repo, "add", perf.CEILINGS)
    _git(repo, "commit", "-q", "-m", "main")
    image = types.SimpleNamespace(stat=lambda: types.SimpleNamespace(st_size=gate.USA.iso_size))
    monkeypatch.setattr(gate, "find", lambda release: image)
    monkeypatch.setattr(web_tools, "wheel", lambda *a, **k: tmp_path / "wheel")
    monkeypatch.setattr(_perf, "venv", lambda *a, **k: "python")
    monkeypatch.setattr(perf, "native_failures", lambda *_: [])
    long, asked = iter([200.0, 100.0]), []

    def drive(wt, spec, todo, *_):   # as _perf.Driver: an op stops at its first sample past 30 s
        asked.append(dict(todo))
        return {"samples": {op: [{"s": next(long), "bar": 2, "progress": True}] if op == "A31" else
                            [{"s": 4.0, "bar": 2, "progress": True}] * n for op, n in todo.items()}, "log": []}
    monkeypatch.setattr(_perf, "drive", drive)
    release = tmp_path / "suite-release.meta"
    release.write_text(json.dumps({"head": "f" * 40, "perf": {"cases": {
        "A31/app": {"median": 60.0}, "A21/app": {"median": 3.0}}}}), encoding="utf-8")
    assert perf.main([str(repo), "--select", "app:build", "--ops", "A31,A21", "--profiles", "app",
                      "--reference", str(release), "--json", str(tmp_path / "perf.json")]) == 1
    cases = json.loads((tmp_path / "perf.json").read_text(encoding="utf-8"))["cases"]
    assert asked == [{"A31": 1, "A21": 1}, {"A21": 2}, {"A31": 1, "A21": 3}]
    assert {k: (r["samples"], r["median"], r["slower"]) for k, r in cases.items()} == {
        "A31/app": ([200.0, 100.0], 150.0, True), "A21/app": ([4.0] * 6, 4.0, True)}


def test_a_changed_areas_perf_run_times_an_op_once_under_1_s_and_mains_run_of_every_op_three_times(tmp_path,
                                                                                                    monkeypatch):
    """P4 (D1215): a changed area's perf run (``--select``) takes one sample
    of each op, and R in all only of one whose sample is at or past 1 s or
    whose page froze; the block's ``one_sample`` names the cases one sample
    judged. Main's run of every op (``--all``) takes R of each."""
    from azurkit.core import gate
    from scripts import web_tools

    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    (repo / perf.CEILINGS).write_text(perf.render(perf.listed(None)), encoding="utf-8")
    _git(repo, "add", perf.CEILINGS)
    _git(repo, "commit", "-q", "-m", "main")
    image = types.SimpleNamespace(stat=lambda: types.SimpleNamespace(st_size=gate.USA.iso_size))
    monkeypatch.setattr(gate, "find", lambda release: image)
    monkeypatch.setattr(web_tools, "wheel", lambda *a, **k: tmp_path / "wheel")
    monkeypatch.setattr(_perf, "venv", lambda *a, **k: "python")
    monkeypatch.setattr(perf, "native_failures", lambda *_: [])
    froze = {"froze": "the page froze 300 ms in the head start before A12"}
    sample = {"A21": {"s": 0.1}, "A13": {"s": 1.5}, "A12": {"s": 0.2} | froze}
    asked = []

    def drive(wt, spec, todo, *_):
        asked.append(dict(todo))
        return {"samples": {op: [sample[op] | {"bar": 0, "progress": True}] * n for op, n in todo.items()}, "log": []}
    monkeypatch.setattr(_perf, "drive", drive)
    for how, drives, n in ((["--select", "app:build"], [{"A21": 1, "A13": 1, "A12": 1}, {"A13": 2, "A12": 2}],
                            {"A21/app": 1, "A13/app": 3, "A12/app": 3}),
                           (["--all"], [{"A21": 3, "A13": 3, "A12": 3}], {"A21/app": 3, "A13/app": 3, "A12/app": 3})):
        asked.clear()
        assert perf.main([str(repo), *how, "--ops", "A21,A13,A12", "--profiles", "app",
                          "--json", str(tmp_path / "perf.json")]) == 0
        block = json.loads((tmp_path / "perf.json").read_text(encoding="utf-8"))
        assert asked == drives, how
        assert {k: r["n"] for k, r in block["cases"].items()} == n
        assert block.get("one_sample") == (["A21/app"] if "--select" in how else None)


def test_a_perf_stage_past_its_cap_stops_perf_py_so_its_scratch_goes(tmp_path, monkeypatch):
    """Step 4.46a: at its cap the perf stage stops perf.py with SIGTERM (it
    SIGKILLed its group), so perf.py's handler runs its finallys, its
    scratch deleted, and the block says it wrote no result, exit 143; one
    that ignores it is ended once :data:`fullsuite.PERF_STOP` passes."""
    scratch, fake = tmp_path / "scratch", tmp_path / "fake_perf.py"
    fake.write_text("import pathlib, shutil, signal, sys, time\n"
                    "signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))\n"
                    f"scratch = pathlib.Path({str(scratch)!r})\nscratch.mkdir()\n"
                    "try:\n    time.sleep(60)\nfinally:\n    shutil.rmtree(scratch)\n", encoding="utf-8")
    real = subprocess.Popen
    monkeypatch.setattr(fullsuite.subprocess, "Popen", lambda argv, **kw: real(   # perf.py's alone (end()'s ps too)
        [sys.executable, str(fake)] if argv[:1] == ["nice"] else argv, **kw))
    monkeypatch.setattr(fullsuite, "PERF_CAP", 3)
    monkeypatch.setattr(perf, "normal_load", lambda: 0.0)
    monkeypatch.setattr(fullsuite, "release_reference", lambda *a: None)
    m = {"worktree": str(tmp_path), "perf_args": ["--select", "app:start"]}
    block = fullsuite.perf_stage(tmp_path / "suite-x.meta", m)
    assert block["failures"] == ["perf.py wrote no result (exit 143): see the log"] and not scratch.exists()
    fake.write_text("import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(60)\n",
                    encoding="utf-8")
    monkeypatch.setattr(fullsuite, "PERF_STOP", 1)
    t0 = time.monotonic()
    assert fullsuite.perf_stage(tmp_path / "suite-y.meta", m)["failures"] == [
        "perf.py wrote no result (exit -9): see the log"] and time.monotonic() - t0 < 30


def test_the_perf_gates_scratch_is_out_of_reach_of_macoss_temp_sweep(tmp_path, monkeypatch):
    """macOS empties $TMPDIR daily of what looks 3 days old, and the app's venv in this scratch keeps uv's cache's times,
    so a run crossing 03:35 would lose its dependencies; Windows, which has no /tmp, takes its temp folder."""
    import tempfile

    from azurkit.core import gate
    from scripts import web_tools

    monkeypatch.setattr(perf.signal, "signal", lambda *_: None)
    monkeypatch.setattr(perf, "R", perf.R)
    monkeypatch.setattr(sys, "path", list(sys.path))
    image = types.SimpleNamespace(stat=lambda: types.SimpleNamespace(st_size=gate.USA.iso_size))
    monkeypatch.setattr(gate, "find", lambda release: image)
    made = []

    def wheel(path, _):
        made.append(path)
        raise InterruptedError("only the scratch's place is asked")
    monkeypatch.setattr(web_tools, "wheel", wheel)
    with pytest.raises(InterruptedError):
        perf.main([str(tmp_path), "--select", "site:build", "--ops", "S05", "--profiles", "site", "--browsers", "firefox"])
    assert made[0].parent.parent == Path(tempfile.gettempdir() if os.name == "nt" else "/tmp")
    assert not made[0].parent.exists()


def test_a_browser_new_to_mains_perf_py_gets_one_first_record_and_nothing_else_grows(tmp_path, monkeypatch):
    """D994: a browser the stack's perf.py times and main's doesn't
    (``perf.new_browsers``) gets one first record: ``--update-ceilings``
    lists its over-budget ops and debts as measured, with no re-run, and
    land.py takes them against main's list; an op added in another context
    is still refused, and so is a new op of that browser once main's perf.py
    times it."""
    repo, _, receipts, _ = _repo(tmp_path, monkeypatch)

    def commit(browsers, lst, what):
        (repo / "scripts").mkdir(exist_ok=True)
        (repo / "tests").mkdir(exist_ok=True)
        (repo / "scripts" / "perf.py").write_text(f"BROWSERS = {browsers!r}\n", encoding="utf-8")
        (repo / perf.CEILINGS).write_text(perf.render(lst), encoding="utf-8")
        _git(repo, "add", "scripts/perf.py", perf.CEILINGS)
        _git(repo, "commit", "-q", "-m", what)
        _receipt(receipts, _git(repo, "rev-parse", "HEAD"), mode="changed", base=_git(repo, "rev-parse", "main"),
                 perf={"passed": True, "cases": {}, "memory": {}, "native_failures": [], "list": []})   # perf.py: timed
    on_main = {"ceilings": {"S05/webkit": 4.0}, "debts": [], "memory": {}, "untimed": {}}
    commit(("webkit", "chromium"), on_main, "main")
    asked = []

    def drive(run, targets):
        asked.append((run, dict(targets)))
        return {"samples": {op: [{"s": 5.0, "bar": 0, "progress": False}] * n for op, n in targets.items()}}
    got, _, _ = perf.measure([("S05", "webkit"), ("S05", "firefox")], drive, on_main, fresh={"firefox"})
    assert asked == [("webkit", {"S05": 3}), ("firefox", {"S05": 3})]
    recorded = perf.updated(on_main, got, {}, False, {"firefox"})
    assert recorded == {**on_main, "ceilings": {"S05/webkit": 4.0, "S05/firefox": 5.8}, "debts": ["S05/firefox"]}
    _git(repo, "switch", "-q", "-c", "p2/y")
    commit(("webkit", "chromium", "firefox"), recorded, "firefox's first record")
    assert perf.new_browsers(repo, "main", "p2/y") == {"firefox"} and perf.new_browsers(repo, "p2/y", "main") == set()
    assert land.land(repo, "p2/y", dry_run=True)[0] == 0
    commit(("webkit", "chromium", "firefox"), {**recorded, "ceilings": {**recorded["ceilings"], "S07/webkit": 4.0}},
           "another op")
    code, why = land.land(repo, "p2/y", dry_run=True)
    assert code == 1 and why.endswith("grows main's list (D981): S07/webkit: added to the list (ceiling 4.0 s)"), why
    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    assert land.land(repo, "p2/y")[0] == 0   # main's perf.py times firefox now
    _git(repo, "switch", "-q", "-c", "p2/z")
    commit(("webkit", "chromium", "firefox"), {**recorded, "ceilings": {**recorded["ceilings"], "S08/firefox": 4.0}},
           "a second record")
    code, why = land.land(repo, "p2/z", dry_run=True)
    assert code == 1 and "S08/firefox: added to the list" in why, why


def test_every_name_the_perf_registrys_functions_call_is_one_the_module_has():
    """tests/_perf.py's drivers run only inside the perf stage, so a helper
    a lane renames elsewhere (python_of, gone with 4.3n's wheel venv) leaves
    a driver that fails only there: each global name a function in the
    module reads is the module's or a builtin."""
    import builtins
    import symtable

    path = Path(_perf.__file__)
    have = set(vars(_perf)) | set(dir(builtins))

    def missing(table: symtable.SymbolTable) -> set[str]:
        out = {s.get_name() for s in table.get_symbols()
               if s.is_global() and s.is_referenced() and s.get_name() not in have}
        for child in table.get_children():
            out |= missing(child)
        return out

    top = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")   # its own names are the module's
    assert set().union(*(missing(child) for child in top.get_children())) == set()


def test_web_tools_downloads_ask_again_over_minutes_after_a_dropped_answer_and_fail_by_name_past_their_tries_or_cap(
        tmp_path, monkeypatch):
    """Step 4.4ci46: a CI job's setup failed on one dropped answer. ``web_tools.download`` (Pyodide's core and its
    wheels) asks a stand-in server again, 15 s after a failed ask, when its first answer ends short of its length or
    closes before its headers, and keeps the whole body; one cut every time fails naming the URL after 6 asks, the
    waits doubling to 2 min (Step 4.5t: GitHub's release downloads answered 504 for minutes, past 3 asks' 15 s), or
    sooner, saying so, where a wait would end past the cap from the first ask; a 404 fails at once, and none leaves a
    part of the file."""
    import http.server
    import threading

    from scripts import web_tools
    body, asked, waits = bytes(range(256)) * 64, [], []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass

        def do_GET(self) -> None:
            asked.append(self.path)
            first = asked.count(self.path) == 1
            if self.path == "/missing":
                return self.send_error(404)
            if self.path == "/silent-once" and first:
                return   # the connection closes with no answer
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            cut = self.path == "/cut-always" or (self.path == "/cut-once" and first)
            self.wfile.write(body[:len(body) // 2] if cut else body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def sleep(seconds: float) -> None:   # the clock moves by the waits alone
        waits.append(seconds)

    monkeypatch.setattr(web_tools, "time", types.SimpleNamespace(sleep=sleep, monotonic=lambda: sum(waits)))
    url, out = f"http://127.0.0.1:{server.server_port}", tmp_path / "file"
    cut = r"; the last: the answer ended at 8,192 of its 16,384 B$"
    try:
        for path in ("/cut-once", "/silent-once"):
            waits.clear()
            assert web_tools.download(url + path, out) == out and out.read_bytes() == body
            assert (asked.count(path), waits) == (2, [15.0]), path
        waits.clear()
        with pytest.raises(SystemExit, match=r"/cut-always: 6 asks failed in 345 s" + cut):
            web_tools.download(url + "/cut-always", out)
        assert (asked.count("/cut-always"), waits, out.exists()) == (6, [15.0, 30.0, 60.0, 120.0, 120.0], False)
        waits.clear()
        monkeypatch.setattr(web_tools, "CAP", 100.0)
        with pytest.raises(SystemExit, match=r"/cut-always: 3 asks failed in 45 s, and a 60 s wait would pass the 100 s "
                                             r"cap" + cut):
            web_tools.download(url + "/cut-always", out)
        assert (asked.count("/cut-always"), waits, out.exists()) == (9, [15.0, 30.0], False)
        with pytest.raises(SystemExit, match=r"/missing: 404 "):
            web_tools.download(url + "/missing", out)
        assert (asked.count("/missing"), waits, out.exists()) == (1, [15.0, 30.0], False)
    finally:
        server.shutdown()
        server.server_close()


def test_ci_resources_prints_the_lowest_room_by_label_and_never_a_path(tmp_path):
    """The runner's room as a CI tier ends (a run the runner shut down named nothing): each label's free disk and the
    free memory, in numbers; never the folders' paths."""
    (tmp_path / "stop").touch()
    done = subprocess.run([sys.executable, "-I", "scripts/ci_resources.py", str(tmp_path / "stop"), f"tier={tmp_path}"],
                          capture_output=True, text=True, timeout=60, cwd=Path(__file__).resolve().parent.parent)
    macos = (r"; Playwright's processes at most [\d.]+ GiB together, one [\d.]+ \([^/\\\n]*\)\n"
             r"--- what macOS wrote of Playwright's processes that ended: [^/\\\n]+\n"
             r"--- what WebKit's log says of a process that ended: [^/\\\n]+\n"
             r"--- the runner's GPU: [^/\\\n]+") if sys.platform == "darwin" else ""
    assert re.fullmatch(r"resources, the lowest of the tier in 0 min: tier [\d.]+ GiB free, temp [\d.]+ GiB free, "
                        rf"memory [\d.]+ GiB free \(memory of [\d.]+\){macos}\n", done.stdout), (done.stdout, done.stderr)


def test_ci_resources_names_playwrights_processes_footprints_and_what_macos_wrote_of_one_that_ended_and_where(
        tmp_path, monkeypatch):
    """A site test's WebKit page that died ("Target crashed", run 41744982709's Apple Silicon pure tier) named nothing
    of its memory: on macOS the watcher reads the footprint of each of Playwright's processes (its command under a
    playwright folder), the count jetsam and WebKit's memory kill read, and at the tier's end names each one that a
    crash report or a jetsam event since the tier began says ended, with its last footprint and the free memory then;
    another process's report, an older one and an unreadable one aren't taken for it. A crash names where it faulted
    (run 41981438506's SIGBUS at 0.52 GiB said only its kind): the address's kind and region, what the process said
    and its crashed thread's innermost frames. Names and numbers only, no path. WebKit's log lines name the IPC message
    its network process refused before it asked for a page process's end (run 42198913490's Intel tier lost a live page
    so, ``reason=RequestedByNetworkProcess``, and the refusal's fault report named no message)."""
    from scripts import ci_resources
    me = (os.getpid(), 1, 5, "node", "/x/.tools/playwright/driver/node run-driver")
    read = ci_resources.footprints([me, (1, 0, 9, "launchd", "/sbin/launchd")])
    if sys.platform != "darwin":
        assert read == {}
    else:
        assert list(read) == [me[0]] and read[me[0]][0] == "node" and 0 < read[me[0]][1] <= read[me[0]][2]
    mine, system = tmp_path / "user", tmp_path / "system"
    for folder in (mine, system):
        folder.mkdir()
    monkeypatch.setattr(ci_resources, "REPORTS", (mine, system))

    def report(folder: Path, name: str, body: dict, age: float = 0) -> None:
        (folder / name).write_text('{"bug_type":"309"}\n' + json.dumps(body), encoding="utf-8")
        os.utime(folder / name, (time.time() - age,) * 2)
    gib, since = 1 << 30, time.time() - 120
    seen = {11: ("com.apple.WebKit.WebContent.Development", 2 * gib, 3 * gib, gib // 2),
            12: ("com.apple.WebKit.WebContent.Development", gib, gib, gib)}
    report(mine, "wc.ips", {"pid": 11, "exception": {"type": "EXC_BAD_ACCESS", "signal": "SIGBUS",
                                                     "subtype": "KERN_PROTECTION_FAILURE at 0x0000000340004000"},
                            "vmRegionInfo": "0x340004000 is in 0x340000000-0x740000000;  bytes after start: 16384\n"
                                            "      REGION TYPE    START - END   [ VSIZE] PRT/MAX SHRMOD  REGION DETAIL\n"
                                            "      MALLOC_SMALL   300000000-300800000 [ 8192K] rw-/rwx SM=PRV\n"
                                            "--->  mapped file    340000000-740000000 [ 16.0G] ---/rwx SM=NUL  "
                                            "/private/tmp/x.bin\n",
                            "asi": {"JavaScriptCore": ["a thread's last words /private/tmp/y"]}, "faultingThread": 1,
                            "usedImages": [{"name": "JavaScriptCore"}, {"name": "WebCore"}],
                            "threads": [{"frames": []}, {"name": "WebCore: Worker", "frames": [
                                {"imageIndex": 0, "symbol": "JSC::Wasm::f"}, {"imageIndex": 1, "imageOffset": 4096},
                                {"imageIndex": 7}] + [{"imageIndex": 0, "symbol": "g"}] * 9}]}, age=3)
    report(mine, "other.ips", {"pid": 99, "exception": {"type": "EXC_CRASH", "signal": "SIGABRT"}}, age=2)
    report(mine, "old.ips", {"pid": 12, "exception": {"type": "EXC_CRASH", "signal": "SIGABRT"}}, age=600)
    (mine / "torn.ips").write_text("{}\n{", encoding="utf-8")   # being written
    report(system, "JetsamEvent.ips", {"memoryStatus": {"pageSize": 16384, "memoryPages": {"free": 32768}},
                                       "processes": [{"pid": 12, "name": "x", "reason": "vm-pageshortage"},
                                                     {"pid": 11, "name": "x"}, {"pid": 98, "reason": "per-process-limit"}]})
    said = ci_resources.reports(since, seen)
    assert said == [
        "com.apple.WebKit.WebContent.Development (id 11) crashed at 2 min: EXC_BAD_ACCESS (SIGBUS); "
        "KERN_PROTECTION_FAILURE at 0x0000000340004000; the address is in mapped file [ 16.0G] ---/rwx SM=NUL; "
        "JavaScriptCore said: a thread's last words; its crashed thread (WebCore: Worker): "
        "JavaScriptCore JSC::Wasm::f < WebCore +0x1000 < ? +0x0 < " + " < ".join(["JavaScriptCore g"] * 5)
        + "; its footprint last read 2.00 GiB (its highest 3.00), memory then 0.5 GiB free",
        "a report of the user's unread (JSONDecodeError)",
        "com.apple.WebKit.WebContent.Development (id 12) killed by jetsam at 2 min: vm-pageshortage, memory 0.5 GiB "
        "free by its count; its footprint last read 1.00 GiB (its highest 1.00), memory then 1.0 GiB free"], said
    log = ("Timestamp               Ty Process[PID:TID]\n2026-11-04 00:36:51.123 E  Playwright[812:9a1] "   # a WebKit kill
           "[com.apple.WebKit:Process] 0x12ab - [pageProxyID=7, webPageID=8, PID=901] WebPageProxy::processDidTerminate: "
           "(pid 901), reason=ExceededMemoryLimit\n2026-11-04 00:36:52.004 E  com.apple.WebKit.Networking.Development"
           "[813:9b2] [com.apple.WebKit:IPC] Received an invalid message NetworkStorageManager_SetItem from WebContent "
           "process 5, requesting for it to be terminated.\n")   # the network process's refusal before it asks for one
    asked = []
    monkeypatch.setattr(ci_resources.subprocess, "run", lambda argv, **_: (asked.append(argv[-1]),
                                                                           types.SimpleNamespace(stdout=log))[1])
    assert ci_resources.webkit_said(since) == [
        "00:36:51 Playwright: [pageProxyID=7, webPageID=8, PID=901] WebPageProxy::processDidTerminate: (pid 901), "
        "reason=ExceededMemoryLimit", "00:36:52 com.apple.WebKit.Networking.Development: Received an invalid message "
        "NetworkStorageManager_SetItem from WebContent process 5, requesting for it to be terminated."]
    assert asked == [ci_resources.ENDINGS] and '"Received an invalid message"' in ci_resources.ENDINGS


SAMPLE_REPORT = """Analysis of sampling com.apple.WebKit.GPU.Development (pid 7) every 1 millisecond
Call graph:
    800 Thread_1   DispatchQueue_1: com.apple.main-thread  (serial)
    + 800 start  (in dyld) + 6992  [0x182dd54e4]
    +   800 xpc_main  (in libxpc.dylib) + 60  [0x18315cfc0]
    +     800 mach_msg2_trap  (in libsystem_kernel.dylib) + 8  [0x18315cc34]
    +     2 other  (in libxpc.dylib) + 8  [0x18315cc35]
    800 Thread_2: RemoteRenderingBackend work queue
    + 800 thread_start  (in libsystem_pthread.dylib) + 8  [0x18319bc1c]
    +   780 WebKit::RemoteImageBuffer::flushContext()  (in WebKit) + 40  [0x1a]  RemoteImageBuffer.cpp:90
    +   ! 780 IOSurfaceLock  (in IOSurface) + 12  [0x1b]
    +   20 IPC::Semaphore::wait()  (in WebKit) + 4  [0x1c]
    800 Thread_3: RemoteRenderingBackend work queue
    + 800 thread_start  (in libsystem_pthread.dylib) + 8  [0x18319bc1c]
    +   780 WebKit::RemoteImageBuffer::flushContext()  (in WebKit) + 40  [0x1a]  RemoteImageBuffer.cpp:90
    +   ! 780 IOSurfaceLock  (in IOSurface) + 12  [0x1b]
    800 Thread_<multiple>   DispatchQueue_9: CA::CG::Queue  (serial)
    + 800 thread_start  (in libsystem_pthread.dylib) + 8  [0x18319bc1c]
    +   800 CA::CG::ContextDelegate::operation_(CGContextDelegate*)  (in QuartzCore) + 12  [0x1d]
    +   ! 800 _dispatch_sync_f_slow  (in libdispatch.dylib) + 168  [0x1e]
    800 Thread_4: JavaScriptCore libpas scavenger
    + 800 thread_start  (in libsystem_pthread.dylib) + 8  [0x18319bc1c]

Total number in stack (recursive counted multiple, when >=5):

Sort by top of stack, same collapsed (when >= 5):
        IOSurfaceLock  (in IOSurface)        1560
        mach_msg2_trap  (in libsystem_kernel.dylib)        800

Binary Images:
       0x1 -        0x2 +com.apple.WebKit.GPU.Development /x/.tools/playwright/webkit/WebKit.framework
"""


def test_ci_resources_names_what_webkits_gpu_process_did_as_it_stopped_answering_and_its_state_each_minute(
        monkeypatch):
    """Run 41818469100's Intel runner ended WebKit's GPU process about 40 times in its WebKit hour (a page's wait on it
    ran out, then each new one left its first message 3 s), every WebKit test after failing, and nothing said what it
    was doing: on macOS the watcher follows WebKit's log as it is written, and the first :data:`SAMPLED` times a line
    says a process stopped answering it samples each of Playwright's GPU processes and the process that wrote it, at
    once, printing each watched thread's heaviest stack (threads alike once, counted) and the calls its threads were
    most often in, never a path, a source line or an address; each minute's line has each GPU process's share of a
    core, page-ins and footprint, WindowServer's share and the load (where the OS keeps one), its own calls read on
    every OS without raising (Windows has no load: run 41981438506); WebKit's lines at the tier's end past the first 20
    are counted by the call that wrote them, its reason and the IPC message refused (a WebKit tier's page closes write
    about 20 harmless refusals, which a line's start merged with the one before a kill, and the kill without its
    reason)."""
    from scripts import ci_resources
    assert ci_resources.stacks(SAMPLE_REPORT) == (
        "main thread: mach_msg2_trap (libsystem_kernel.dylib) < xpc_main (libxpc.dylib) < start (dyld); 2 x "
        "RemoteRenderingBackend work queue: IOSurfaceLock (IOSurface) < WebKit::RemoteImageBuffer::flushContext() "
        "(WebKit) < thread_start (libsystem_pthread.dylib); CA::CG::Queue: _dispatch_sync_f_slow (libdispatch.dylib) < "
        "CA::CG::ContextDelegate::operation_(CGContextDelegate*) (QuartzCore) < thread_start (libsystem_pthread.dylib); "
        "most often in: IOSurfaceLock (IOSurface) 1560, "
        "mach_msg2_trap (libsystem_kernel.dylib) 800")
    monkeypatch.setattr(ci_resources, "sampled", lambda pid: f"stacks of {pid}")
    read = {7: ("com.apple.WebKit.GPU.Development", 100 << 20, 0), 8: ("com.apple.WebKit.WebContent.Development", 1, 1)}
    gone = "GPUProcessProxy::didBecomeUnresponsive: GPUProcess with PID 7 became unresponsive"
    rows = [f"2026-11-04 13:59:{s}.1 E  {who}[{pid}:9a1] [com.apple.WebKit:Process] 0x12ab - {what}\n"
            for s, who, pid, what in (
                ("30", "Playwright", 5, "WebPageProxy::processDidTerminate: reason=Crash"),
                ("34", "com.apple.WebKit.WebContent.Development", 8,
                 "[renderingBackend=11] RemoteRenderingBackendProxy::didBecomeUnresponsive"),
                ("53", "Playwright", 5, gone), ("57", "Playwright", 5, gone))]
    said, left = ci_resources.stuck(rows, read, 2)
    assert (said, left) == ([
        "--- WebKit's log at 13:59:34, com.apple.WebKit.WebContent.Development: [renderingBackend=11] "
        "RemoteRenderingBackendProxy::didBecomeUnresponsive; com.apple.WebKit.GPU.Development (id 7) sampled 1 s: "
        "stacks of 7",
        "--- WebKit's log at 13:59:34, com.apple.WebKit.WebContent.Development: [renderingBackend=11] "
        "RemoteRenderingBackendProxy::didBecomeUnresponsive; com.apple.WebKit.WebContent.Development (id 8) sampled "
        "1 s: stacks of 8",
        f"--- WebKit's log at 13:59:53, Playwright: {gone}; com.apple.WebKit.GPU.Development (id 7) sampled 1 s: "
        "stacks of 7"], 0)
    load = r"[\d.]+" if hasattr(os, "getloadavg") else "unread"   # Windows keeps no load (run 41981438506)
    assert (ci_resources.cpu_used(os.getpid()) is None) == (sys.platform != "darwin")   # macOS's call, none elsewhere
    assert re.fullmatch(rf"; WebKit's GPU processes: none; WindowServer (?:0% of a core|unread); load {load}",
                        ci_resources.gpu_state({}, {}, 0.0))   # this OS's own calls
    used = iter([(10.0, 40), (40.0, 43)])
    monkeypatch.setattr(ci_resources, "cpu_used", lambda pid: next(used))
    monkeypatch.setattr(ci_resources, "cpu_used_ps", lambda name: 100.0 if name == "WindowServer" else None)
    then = {}
    ci_resources.gpu_state(read, then, 0.0)
    assert re.fullmatch(rf"; WebKit's GPU processes: id 7 50% of a core, 3 page-ins, 100 MiB; WindowServer 0% of a "
                        rf"core; load {load}", ci_resources.gpu_state(read, then, 60.0))
    calls = ("didBecomeUnresponsive: x", "gpuProcessExited: reason=Unresponsive")
    log = "".join(f"2026-11-04 14:{m:02}:00.1 E  Playwright[5:9a1] [com.apple.WebKit:Process] 0x1 - "
                  f"GPUProcessProxy::{calls[m % 2]}\n" for m in range(25))
    log += "".join(f"2026-11-04 14:{m}:00.1 E  com.apple.WebKit.Networking.Development[6:9b2] [com.apple.WebKit:IPC] "
                   f"Received an invalid message NetworkStorageManager_{name} from WebContent process 8, requesting "
                   "for it to be terminated.\n" for m, name in ((25, "DatabaseConnectionClosed"), (26, "SetItem")))
    log += "".join(f"2026-11-04 14:26:00.2 E  Playwright[5:9a1] [com.apple.WebKit:Process] 0x1 - [pageProxyID=7] "
                   f"WebPageProxy::processDidTerminate: (pid 8), reason={why}\n"
                   for why in ("Crash", "RequestedByNetworkProcess"))
    monkeypatch.setattr(ci_resources.subprocess, "run", lambda *_, **__: types.SimpleNamespace(stdout=log))
    assert ci_resources.webkit_said(0)[20:] == [
        "and 9 more; all 29 by the call that wrote them: GPUProcessProxy::didBecomeUnresponsive 13 (the last at "
        "14:24:00), GPUProcessProxy::gpuProcessExited reason=Unresponsive 12 (the last at 14:23:00), invalid message "
        "NetworkStorageManager_DatabaseConnectionClosed 1 (the last at 14:25:00), invalid message "
        "NetworkStorageManager_SetItem 1 (the last at 14:26:00), WebPageProxy::processDidTerminate reason=Crash 1 (the "
        "last at 14:26:00), WebPageProxy::processDidTerminate reason=RequestedByNetworkProcess 1 (the last at "
        "14:26:00)"]


def test_ci_resources_stops_a_tier_whose_log_stops_growing_its_workers_before_pytest_once_it_printed_the_logs_tail(
        tmp_path):
    """A CI tier that hangs names itself (run 41521288667: Windows' tier sat silent 3.5 h until the job's limit cut it
    off, its log never printed). A log that grows is never quiet; one that stays the same size for the stall time
    stops the tier: the watcher prints the log's last 200 lines, each cut at 240 characters, and the tier's processes
    under it with their ages, then ends xdist's workers (execnet's command line) and only after a while what is
    left, so pytest's controller still writes its summary and failures to the log (Step 4.4ci12's review, F1), and
    exits 3 once STOP exists, so the step fails with time left. The watcher writes to files, as CI's runner reads a
    step's output as it comes: it prints all that before it ends anything, and a pipe read only once the tier ended
    holds about 4 KiB on Windows, so its print waited on the test that waited on the tier (tests.yml run 42122369507).
    No listing of every process holds the stop (run 42146627936's Windows tier was unended in 90 s, each of the
    watcher's reads of it a CIM query of every process through PowerShell): here one that doesn't answer in 100 s,
    the minute line's on macOS, keeps the watcher neither from ending the tier nor from exiting."""
    from execnet.gateway_io import popen_bootstrapline
    from scripts import ci_resources
    log, stop, stall = tmp_path / "pytest.log", tmp_path / "stop", ci_resources.STALL_S
    growth = ci_resources.Growth(str(log), now=0.0)
    log.write_text("collected\n")
    assert growth.quiet(stall) == 0.0                     # it appeared: grown
    assert growth.quiet(2 * stall - 1) == stall - 1       # still one test running
    log.write_text("collected\n.")
    assert growth.quiet(2 * stall) == 0.0                 # a test ended
    assert growth.quiet(3 * stall) == stall               # quiet for the stall time: stalled
    log.write_text("".join(f"line {i}\n" for i in range(300)) + "x" * 300 + "\n")
    fake = tmp_path / "tier.py"
    fake.write_text(f"""import os, subprocess, sys, time
if sys.argv[1] == "tier":   # the step's subshell, which only ends when it is ended
    subprocess.Popen([sys.executable, __file__, "pytest"])
else:   # pytest's controller: once its worker has ended, it writes its summary, then hangs
    worker = subprocess.Popen([sys.executable, "-u", "-c", {popen_bootstrapline!r}], stdin=subprocess.PIPE, text=True)
    worker.stdin.write(repr("import time; time.sleep(300)") + "\\n")
    worker.stdin.flush()
    print(os.getpid(), worker.pid, flush=True)
    worker.wait()
    with open({str(log)!r}, "a") as f:
        f.write("the summary\\n")
time.sleep(300)
""")
    tier = subprocess.Popen([sys.executable, str(fake), "tier"], stdout=subprocess.PIPE, text=True)
    controller, worker = map(int, tier.stdout.readline().split())
    said, warned = tmp_path / "watcher.out", tmp_path / "watcher.err"
    slow = ("import sys, time; sys.path.insert(0, sys.argv.pop(1)); from scripts import ci_resources; "
            "ci_resources.processes = lambda *_, **__: time.sleep(100); sys.exit(ci_resources.main(sys.argv[1:]))")
    with open(said, "wb") as stdout, open(warned, "wb") as stderr:
        watcher = subprocess.Popen([sys.executable, "-I", "-c", slow, str(ROOT), str(stop), f"--watch={log}",
                                    f"--tier={tier.pid}", "--stall=2", f"tier={tmp_path}"],
                                   stdout=stdout, stderr=stderr, cwd=ROOT)
    try:
        ended = tier.wait(timeout=90)
    except subprocess.TimeoutExpired:
        ended = None
    finally:
        stop.touch()
        watcher.wait(timeout=90)
        out, err = said.read_text(errors="replace"), warned.read_text(errors="replace")
        if tier.poll() is None:
            tier.kill()
            for pid in (controller, worker):
                try:
                    os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
                except OSError:
                    pass
        tier.stdout.close()
    assert ended is not None, ("the watcher didn't end the tier in 90 s", out, err)
    assert watcher.returncode == 3, (out, err)
    printed = out.split("--- the tier's log hasn't grown in 0 min: the log's last 200 lines\n")[1]
    assert printed.split("\n--- the tier's processes")[0].split("\n") == [f"line {i}" for i in range(101, 300)] + [
        "x" * 240], out
    assert re.search(rf"^\S*python\S* \(id {tier.pid}\): 0 min, \d+ MiB$", out, re.M | re.I), out
    for pid in (controller, worker):
        assert re.search(rf"^ +\S*python\S* \(id {pid}\): 0 min, \d+ MiB$", out, re.M | re.I), out
    assert log.read_text().splitlines()[-1] == "the summary", out   # pytest outlived its worker
    assert "--- the tier stopped" in out, out                       # and was ended once it hung on
    for _ in range(50):
        if not {controller, worker} & {row[0] for row in ci_resources.processes()}:
            break
        time.sleep(0.2)
    else:
        raise AssertionError(f"pytest's controller {controller} or its worker {worker} still runs")


# Step 4.28b: Modkit's unpinned dev tool behaviour, ported lean.


def test_restack_runs_its_batch_work_at_nice_15_or_lower_priority_and_only_in_a_lane(monkeypatch):
    """Modkit's Step X.81a: a restack's batch work took every CPU at nice 0
    beside the gate's pytest at nice 10. ``devkit rando restack`` renices
    itself to 15 before any step (each process it starts inherits it), from
    0 or the gate's 10, and leaves a lower priority as it is. Windows has no
    nice (Step 4.37j: ``os.nice`` failed there): its priority class goes
    below normal the same way, an idle one left as it is. In the main
    checkout it refuses, exit 2, before any change of priority or any step."""
    from devkit.rando import restack

    priority, ran, normal = [0], [], 0x20            # <winbase.h>'s NORMAL_PRIORITY_CLASS
    lane, main = "/lane/.git/worktrees/x\n/lane/.git\n", "/main/.git\n/main/.git\n"

    def nice(by: int) -> int:
        priority[0] = min(19, priority[0] + by)
        return priority[0]

    def set_class(handle, cls: int) -> int:
        assert handle == -1                            # the pseudo-handle of this process
        priority[0] = cls
        return 1

    kernel32 = types.SimpleNamespace(GetCurrentProcess=lambda: -1, GetPriorityClass=lambda handle: priority[0],
                                     SetPriorityClass=set_class)
    monkeypatch.setattr(restack.os, "nice", nice, raising=False)    # none on Windows: the stand-in's alone
    monkeypatch.setattr(restack, "_kernel32", lambda: kernel32)
    monkeypatch.setattr(restack, "restack", lambda *args: ran.append(priority[0]))
    below, idle = restack.BELOW_NORMAL, restack.IDLE
    for windows, start, dirs, want in ((False, 0, lane, (0, [15])), (False, 10, lane, (0, [15])),
                                       (False, 19, lane, (0, [19])), (False, 0, main, (2, [])),
                                       (True, normal, lane, (0, [below])), (True, below, lane, (0, [below])),
                                       (True, idle, lane, (0, [idle])), (True, normal, main, (2, []))):
        priority[0], ran[:] = start, []
        monkeypatch.setattr(restack, "WINDOWS", windows)
        monkeypatch.setattr(restack.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, dirs, ""))
        assert (restack.main([]), ran) == want, (windows, start)
        assert priority[0] == (want[1] or [start])[0]


# --- Step 4.28f: Modkit's unpinned dev-tool behaviours, ported -------------------------------------------------


def test_devlog_release_joins_each_entry_once_in_order_and_deletes_its_files(tmp_path):
    """A release (``scripts/devlog.py --release TITLE --remove``, Modkit's
    Step 2.212) writes the entries into DEVLOG.md as one section above the
    newest release, Keep a Changelog's sections in order and each one's
    files by name with numbers compared as numbers, and deletes the files;
    an entry written again after it, or the old way, is refused."""
    log, folder = tmp_path / "docs" / "DEVLOG.md", tmp_path / "docs" / "devlog"
    entries = {"fixed/2.10-later.md": "- **B** (Step 2.10): b.\n",
               "fixed/2.9-first.md": "- **A** (Step 2.9): a\n  wrapped.\n",
               "added/x.1-new.md": "- **C** (Step X.1): c.\n"}
    for rel, text in entries.items():
        (folder / rel).parent.mkdir(parents=True, exist_ok=True)
        (folder / rel).write_text(text, encoding="utf-8")
    log.write_text("# Developer log\n\n## [Unreleased]\n\nSee devlog/.\n\n## [v1]\n\n### Fixed\n- old.\n",
                   encoding="utf-8")
    assert devlog.release(tmp_path, "v2", remove=True).endswith("deleted their 3 files")
    assert log.read_text(encoding="utf-8") == (
        "# Developer log\n\n## [Unreleased]\n\nSee devlog/.\n\n## [v2]\n\n### Added\n- **C** (Step X.1): c.\n\n"
        "### Fixed\n- **A** (Step 2.9): a\n  wrapped.\n- **B** (Step 2.10): b.\n\n## [v1]\n\n### Fixed\n- old.\n")
    assert not (folder / "fixed").exists() and devlog.problems(tmp_path) == []
    (folder / "fixed").mkdir()
    (folder / "fixed" / "2.9-again.md").write_text(entries["fixed/2.9-first.md"], encoding="utf-8")
    log.write_text(log.read_text(encoding="utf-8").replace("devlog/.\n", "devlog/.\n- **D** (Step 3.1): d.\n"),
                   encoding="utf-8")
    old_way, again = devlog.problems(tmp_path)
    assert old_way.startswith("docs/DEVLOG.md:6: an entry under [Unreleased], the old way: each entry is its own "
                              "file, docs/devlog/<added|changed|removed|fixed>/<step>-<slug>.md")
    assert again == "docs/devlog/fixed/2.9-again.md: the same entry as docs/DEVLOG.md:14, released; keep one"
    with pytest.raises(devlog.Refused, match="docs/devlog/fixed/2.9-again.md: the same entry"):
        devlog.release(tmp_path, "v3")

"""``python -m devkit re test-for-va TARGET [--run]``: the tests that pin a
VA or a pack, and optionally pytest on just those (Modkit's ``azurik-mod
test-for-va``, ported in Step 4.11e onto the facts, the goldens and
``scripts/fullsuite.py``'s import graph).

``TARGET`` is a VA (the USA one, hex or decimal) or a name (a pack's, a
facts function's, any bareword). A test is picked, each with why:

- **spelled:** a ``tests/**/test_*.py`` source holds the VA as ``0x<HEX>``
  at any width from 4 to 8 digits (case-blind), or the name as a bareword,
  or for a VA the name of the facts function at it. Each hit selects the
  pytest node it sits in, read with :mod:`ast`: the ``test*`` function
  holding it (``Class::test_x`` for a method of a test class); else the test
  class; else the module (a constant or a helper).
- **the facts:** a VA in a section's file bytes is pinned by
  :data:`FACTS_TEST` (the facts' XBE half, every section's and site's
  sha256, derived from each image). A VA in a USA facts site (or a site
  that starts within the longest instruction after it: the facts record
  only the bytes a pack changes) is pinned by :data:`SITES_TEST`, Europe's
  case too where Europe's facts have the site; and the packs whose cases of
  ``tests/goldens/sites.json`` write it are its packs.
- **a pack** (the name, or a VA's packs): :data:`G1_TEST` builds its cases
  (Europe's too where it lists Europe), :data:`SITES_TEST` checks its XBE
  sites, :data:`G2_TEST` its prebuilt shim (a trampoline's, or one named
  after it that its ``custom_apply`` lands); and fullsuite's graph picks each test
  file that imports its module other than through the registry
  (:data:`REGISTRY`, which every build's test reaches).

The nodes are pytest's own (``file::test[param]``); ``--run`` passes them
to ``python -m pytest`` with any arguments after ``--``.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SITES_TEST = "tests/test_packs.py::test_each_ported_case_writes_the_facts_bytes_site_by_site_and_nothing_else"
G1_TEST = "tests/test_packs.py::test_each_g1_case_of_a_ported_pack_builds_its_golden_and_its_preset_carries_it_back"
G2_TEST = "tests/test_shims.py::test_each_prebuilt_shim_is_its_sources_build_and_holds_its_g2_hash"
FACTS_TEST = "tests/test_packs.py::test_the_shipped_facts_xbe_half_is_the_one_gen_facts_reads_from_each_image"
NODES = (SITES_TEST, G1_TEST, G2_TEST, FACTS_TEST)   # the nodes the facts and goldens tie a target to
REGISTRY = frozenset({"azurkit.tools.mods", "azurkit.tools.mods.packs"})   # every pack reaches a build's tests here
_MAX_INSTRUCTION = 15  # bytes: the longest x86 instruction


@dataclass(frozen=True)
class TestMatch:
    """One pytest node that pins the target: ``file`` relative to the
    checkout (the tests directory's parent), ``node`` ``""`` for a whole
    module, ``hit_lines`` the lines that spell it (none: ``why`` says)."""

    __test__ = False   # not a pytest test class

    file: Path
    node: str
    hit_lines: tuple[int, ...]
    why: str = "spelled"

    def pytest_selector(self) -> str:
        """A ``tests/foo.py[::Node]`` spec pytest can consume."""
        path = self.file.as_posix()
        return f"{path}::{self.node}" if self.node else path


def _build_va_patterns(va: int) -> list[re.Pattern[str]]:
    """Regexes that match a VA written as hex at any common width (4 to 8
    digits), the prefix and the digits case-blind, as a whole word:
    ``x = 0x85f62`` matches, ``foo_0x85F62_bar`` doesn't."""
    out: list[re.Pattern[str]] = []
    for width in (4, 5, 6, 7, 8):
        fmt = f"0x{va:0{width}X}"
        pat = re.compile(
            rf"\b{re.escape(fmt)}\b".replace("\\x", "[xX]"),
            re.IGNORECASE)
        out.append(pat)
    return out


def _build_name_pattern(name: str) -> re.Pattern[str]:
    """Match ``name`` as a bareword (no leading / trailing
    alphanumeric or underscore)."""
    return re.compile(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])")


def _is_test_def(node: ast.stmt) -> bool:
    return (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test"))


def _is_test_class(node: ast.stmt) -> bool:
    """A ``Test*`` class or a ``*TestCase`` subclass with a ``test*``
    method of its own.  A hit in any other class (a helper, or a
    subclass pytest may not collect) selects the module."""
    if not (isinstance(node, ast.ClassDef)
            and any(_is_test_def(m) for m in node.body)):
        return False
    bases = (b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
             for b in node.bases)
    return node.name.startswith("Test") or any(b.endswith("TestCase") for b in bases)


def _span(node: ast.stmt, name: str) -> tuple[int, int, str]:
    first = min([node.lineno] + [d.lineno for d in node.decorator_list])
    return first, node.end_lineno, name


def _test_spans(tree: ast.Module) -> list[tuple[int, int, str]]:
    """``(first_line, last_line, node)`` for every test function, test
    class and test method in a module, decorators included."""
    spans: list[tuple[int, int, str]] = []
    for node in tree.body:
        if _is_test_def(node):
            spans.append(_span(node, node.name))
        elif _is_test_class(node):
            spans.append(_span(node, node.name))
            spans += [_span(m, f"{node.name}::{m.name}")
                      for m in node.body if _is_test_def(m)]
    return spans


def _spelled(patterns: list[re.Pattern[str]], tests_dir: Path) -> dict[tuple[Path, str], set[int]]:
    matches: dict[tuple[Path, str], set[int]] = {}
    for py in sorted(tests_dir.rglob("test_*.py")):
        try:
            source = py.read_text(encoding="utf-8")
            spans = _test_spans(ast.parse(source, filename=str(py)))
        except (UnicodeDecodeError, SyntaxError) as exc:
            raise ValueError(f"{py}: {exc}") from exc
        for pat in patterns:
            for m in pat.finditer(source):
                line_no = source.count("\n", 0, m.start()) + 1
                # The innermost span holding the hit starts last.
                node = max((s for s in spans if s[0] <= line_no <= s[1]),
                           default=(0, 0, ""))[2]
                matches.setdefault((py, node), set()).add(line_no)
    return matches


def _node(tests_dir: Path, node: str, release: str | None = None) -> tuple[Path, str]:
    """A :data:`NODES` entry as ``(file, node)`` under ``tests_dir``, with its release's parameter."""
    path, _, name = node.partition("::")
    return tests_dir / Path(path).name, f"{name}[{release}]" if release else name


def _site_packs(va: int) -> tuple[set[str], set[str]]:
    """The releases whose facts have a site holding ``va`` (or starting just
    after it) and the packs whose ``sites.json`` cases write those sites."""
    from azurkit.core import facts, gate
    from scripts import record_goldens

    usa, europe = facts.of(gate.USA), facts.of(gate.EUROPE)
    sites = ([s for s in usa.sites.values() if s.va <= va < s.va + s.size]
             or [s for s in usa.sites.values() if va < s.va < va + _MAX_INSTRUCTION])
    if not sites:
        return set(), set()
    keys = {f"0x{s.va:08X}" for s in sites}
    golden, cases = record_goldens.recorded("sites.json"), record_goldens.cases("sites.json")
    packs = {cases[case]["pack"] for case, spans in golden.items() if keys & spans.keys()}
    releases = {"usa"} | {"europe" for s in sites if europe.addresses.get(s.va) in europe.sites}
    return releases, packs


def find_matches(target: int | str, tests_dir: Path, deps: dict | None = None) -> list[TestMatch]:
    """The pytest nodes that pin ``target``, a VA (an int) or a name (the
    module's list). ``deps`` is fullsuite's graph (``scripts.fullsuite.graph``
    of ``tests_dir``'s checkout when a pack needs it and none is given)."""
    import shimkit
    from azurkit.core import facts, gate
    from azurkit.tools import mods
    from azurkit.tools.mods.engine import XBE, TrampolinePatch

    found: dict[tuple[Path, str], tuple[set[int], str]] = {}

    def add(key: tuple[Path, str], why: str, lines=()) -> None:
        have = found.setdefault(key, (set(), why))
        have[0].update(lines)

    packs: set[str] = set()
    if isinstance(target, int):
        usa = facts.of(gate.USA)
        names = [f.name for f in usa.functions.values() if f.va == target]
        patterns = _build_va_patterns(target) + [_build_name_pattern(n) for n in names]
        if any(s.va <= target < s.va + min(s.vsize, s.raw_size) for s in usa.sections):
            add(_node(tests_dir, FACTS_TEST), "the facts' sections")
        releases, packs = _site_packs(target)
        for release in sorted(releases):
            add(_node(tests_dir, SITES_TEST, release), "the facts' site")
    else:
        patterns = [_build_name_pattern(target)]
        packs = {target} & mods.PACKS.keys()
    for key, lines in _spelled(patterns, tests_dir).items():
        add(key, "spelled", lines)

    for name in sorted(packs):
        pack = mods.PACKS[name]
        for release in pack.releases:
            add(_node(tests_dir, G1_TEST, release), f"G1 builds {name}")
            if XBE in pack.files():
                add(_node(tests_dir, SITES_TEST, release), f"{name}'s sites")
        if any(isinstance(s, TrampolinePatch) for s in pack.sites) or (shimkit.SHIMS / f"{name}.o").is_file():
            add(_node(tests_dir, G2_TEST), f"{name}'s shim")
        if deps is None:
            from scripts import fullsuite
            deps = fullsuite.graph(tests_dir.parent)
        for path in importers(deps, _module_of(pack)):
            add((tests_dir.parent / path, ""), f"imports {name}")

    return [TestMatch(path.relative_to(tests_dir.parent), node, tuple(sorted(lines)), why)
            for (path, node), (lines, why) in sorted(found.items())]


def _module_of(pack) -> str:
    """The module under ``azurkit.tools.mods.packs`` that defines ``pack``
    (one module may hold several: ``qol_popups``, ``qol_memory``)."""
    import azurkit.tools.mods.packs as packs   # the registry imported every pack module

    return next(name for name, mod in sorted(sys.modules.items())
                if name.startswith(f"{packs.__name__}.") and any(v is pack for v in vars(mod).values()))


def importers(deps: dict, module: str) -> list[str]:
    """The test files (``tests/test_x.py``) that import ``module`` directly
    or through other modules, fullsuite's graph ``deps`` (``{module: what it
    uses}``) read backwards, never through :data:`REGISTRY`."""
    seen, todo = {module}, [module]
    while todo:
        m = todo.pop()
        for user, uses in deps.items():
            if m in uses and user not in seen and user not in REGISTRY:
                seen.add(user)
                todo.append(user)
    return sorted(f"{m.replace('.', '/')}.py" for m in seen if m.startswith("tests.test_"))


def run_pytest(matches: list[TestMatch], extra_args: list[str], cwd: Path = ROOT) -> int:
    """Run pytest in ``cwd`` (the checkout the matches' paths are from) on
    the matches and return its exit code; 5 (pytest's "no tests ran") when
    there are none."""
    if not matches:
        return 5
    sys.stdout.flush()  # the selection listing prints before pytest's output
    return subprocess.run([sys.executable, "-m", "pytest",
                           *(m.pytest_selector() for m in matches),
                           *extra_args], cwd=cwd).returncode


def main(argv: list[str]) -> int:
    """Print the nodes (``--json``: a list); ``--run``: exit with pytest's
    code. A tests directory that isn't one, or a test file that doesn't
    parse, is one line and exit 2."""
    extra = argv[argv.index("--") + 1:] if "--" in argv else []
    argv = argv[:argv.index("--")] if "--" in argv else argv
    p = argparse.ArgumentParser(
        prog="python -m devkit re test-for-va",
        description="Find the tests that pin a VA or a pack: those whose source spells it (the VA, the facts "
                    "function at it, the name), the facts' and goldens' tests that pin its site and its packs, and "
                    "the test files that import a pack's module. --run runs pytest on just those (arguments after "
                    "-- go to pytest).")
    p.add_argument("target", help="a USA VA (0x85F62, or decimal) or a name: a pack's, a facts function's, a word")
    p.add_argument("--run", action="store_true", help="run pytest on the matches (default: just print them)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--tests-dir", help="the tests directory (default: the checkout's tests/)")
    args = p.parse_args(argv)

    tests_dir = Path(args.tests_dir).resolve() if args.tests_dir else ROOT / "tests"
    if not tests_dir.is_dir():
        print(f"test-for-va: tests directory not found: {tests_dir}", file=sys.stderr)
        return 2
    try:
        target: int | str = int(args.target, 0)
    except ValueError:
        target = args.target
    try:
        matches = find_matches(target, tests_dir)
    except ValueError as exc:
        print(f"test-for-va: {exc}", file=sys.stderr)
        return 2

    what = f"VA {target:#x}" if isinstance(target, int) else repr(target)
    if args.json:
        print(json.dumps([{"file": m.file.as_posix(), "node": m.node, "selector": m.pytest_selector(),
                           "hit_lines": list(m.hit_lines), "why": m.why} for m in matches], indent=2))
    elif not matches:
        print(f"(no tests pin {what})")
    else:
        print(f"{len(matches)} pytest node(s) pin {what}:")
        for m in matches:
            hint = (f"lines: {', '.join(map(str, m.hit_lines[:4]))}" + ("..." if len(m.hit_lines) > 4 else "")
                    if m.hit_lines else m.why)
            print(f"  {m.pytest_selector()}  ({hint})")
    return run_pytest(matches, extra, tests_dir.parent) if args.run else 0


__all__ = [
    "TestMatch",
    "find_matches",
    "importers",
    "run_pytest",
]

"""The engine's contracts: import-linter's (``pyproject.toml``: the layers and
the three tools' independence) and the rules it can't express, read from the
AST: ``core``, ``edits`` and ``tools`` hold no threads, processes,
subprocesses, prints or exits (the web page's worker runs them as they are;
the app-only ``tools/randomizer/live/`` is exempt), only ``tools/characters``
imports numpy, and nothing imports capstone, unicorn, zig or Tk (none of them
ships)."""

from __future__ import annotations

import ast
from pathlib import Path

from importlinter.cli import lint_imports

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "azurkit"
ENGINE = ("core/", "edits/", "tools/")
APP_ONLY = ("tools/randomizer/live/",)
ENGINE_IMPORTS = {"threading", "_thread", "multiprocessing", "concurrent", "subprocess", "asyncio"}
ENGINE_CALLS = {"print", "exit", "quit", "sys.exit", "os._exit", "os.system", "os.popen", "os.fork", "os.forkpty",
                "os.kill"}
ENGINE_CALL_PREFIXES = ("os.spawn", "os.exec", "os.posix_spawn")
NEVER = {"capstone", "unicorn", "ziglang", "tkinter"}
NUMPY_HOME = "tools/characters/"


def violations(source: str, rel: str) -> list[str]:
    """``"<rel>:<line> <why>"`` for each contract the module ``rel`` (a path
    under ``src/azurkit/``) breaks."""
    engine = rel.startswith(ENGINE) and not rel.startswith(APP_ONLY)
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        for name in names:
            top = name.split(".")[0]
            if top in NEVER or (top == "numpy" and not rel.startswith(NUMPY_HOME)):
                found.append(f"{rel}:{node.lineno} imports {name}")
            elif engine and (top in ENGINE_IMPORTS or name in ENGINE_CALLS
                             or name.startswith(ENGINE_CALL_PREFIXES)):
                found.append(f"{rel}:{node.lineno} imports {name}")
        if engine and isinstance(node, ast.Call):
            called = ast.unparse(node.func)
            if called in ENGINE_CALLS or called.startswith(ENGINE_CALL_PREFIXES):
                found.append(f"{rel}:{node.lineno} calls {called}")
    return found


def test_import_linter_contracts_hold(capsys):
    assert lint_imports(config_filename=str(ROOT / "pyproject.toml"), no_cache=True) == 0, capsys.readouterr().out


def test_the_engine_holds_no_threads_processes_prints_or_exits_and_numpy_stays_in_characters():
    caught = {   # each form the rules name, in an engine module
        "import threading": "imports threading",
        "from concurrent.futures import ThreadPoolExecutor": "imports concurrent.futures",
        "import subprocess as sp": "imports subprocess",
        "from os import fork": "imports os.fork",
        "print('x')": "calls print",
        "import sys\nsys.exit(1)": "calls sys.exit",
        "os.execv('a', [])": "calls os.execv",
        "import numpy as np": "imports numpy",
        "from capstone import Cs": "imports capstone",
    }
    for source, why in caught.items():
        assert any(v.endswith(why) for v in violations(source, "core/x.py")), source
    assert violations("import numpy\nimport threading", "tools/randomizer/live/x.py") == [
        "tools/randomizer/live/x.py:1 imports numpy"]
    assert violations("import numpy\nprint(numpy)", "cli.py") == ["cli.py:1 imports numpy"]
    assert violations("import numpy", "tools/characters/body.py") == []
    found = [v for path in sorted(SRC.rglob("*.py"))
             for v in violations(path.read_text(encoding="utf-8"), path.relative_to(SRC).as_posix())]
    assert found == []
